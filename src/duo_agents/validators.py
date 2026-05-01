"""Validation utilities for subagents, managed-agent configs, and bundles.

This module replaces the jsonschema-based logic that previously lived in
``scripts/validate_subagents.py`` / ``scripts/validate-config.py`` /
``scripts/validate-bundle.py``. The CLI scripts now delegate to the
functions defined here.

Error message formatting is preserved so that pre-commit hooks, CI logs and
the existing test suite keep working unchanged.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from duo_agents.config.paths import (
    BUNDLES_DIR,
    MANIFEST_PATH,
    REPO_ROOT,
    SUBAGENTS_DIR,
)
from duo_agents.schemas import (
    Bundle,
    ManagedAgentConfig,
    SubagentFrontmatter,
    format_validation_error,
)

# YAML frontmatter pattern (head ``---\n...\n---\n``).
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

# Frontmatter fields known to Claude Code v2.1+ (kept for legacy callers
# that report a ``[unknown-fields]`` warning before pydantic raises).
KNOWN_FRONTMATTER_FIELDS: frozenset[str] = frozenset(SubagentFrontmatter.model_fields.keys())


# ── Frontmatter parsing ──────────────────────────────────────────────────────


def extract_frontmatter(filepath: Path) -> tuple[dict[str, Any] | None, str | None]:
    """Read ``filepath`` and parse its leading YAML frontmatter block.

    Returns ``(data, None)`` on success, or ``(None, error_message)`` on
    failure. The error string preserves the wording used by the legacy
    validator so that existing tests keep matching.
    """
    text = filepath.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(text)
    if not match:
        return None, "YAML frontmatter が見つかりません（ファイル先頭の --- ... --- ブロック）"

    try:
        data = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        return None, f"YAML パースエラー: {exc}"

    if not isinstance(data, dict):
        return None, f"frontmatter がオブジェクトではありません（型: {type(data).__name__}）"

    return data, None


# ── Subagent frontmatter validation ──────────────────────────────────────────


def validate_subagent_frontmatter(data: dict[str, Any], filepath: Path) -> list[str]:
    """Validate subagent frontmatter ``data`` and return error messages.

    The list is empty on success. Each entry is preformatted with leading
    indentation so callers can ``print`` them as-is.
    """
    errors: list[str] = []

    # 1. Pydantic structural / type validation.
    try:
        SubagentFrontmatter.model_validate(data)
    except ValidationError as exc:
        errors.extend(format_validation_error(exc))

    # 2. ``name`` must equal directory / file stem.
    expected_name = filepath.parent.name if filepath.name == "agent.md" else filepath.stem
    if "name" in data and data["name"] != expected_name:
        errors.append(
            f"  [name] frontmatter の name '{data['name']}' が '{expected_name}' と一致しません"
        )

    # 3. Body must not be empty.
    text = filepath.read_text(encoding="utf-8")
    body = FRONTMATTER_RE.sub("", text).strip()
    if not body:
        errors.append("  [body] frontmatter 以降のシステムプロンプト（本文）が空です")

    return errors


# ── Managed Agent config validation ──────────────────────────────────────────


def _extract_agent_md(agent_dir: Path) -> tuple[dict[str, Any] | None, str | None, str | None]:
    """Return ``(frontmatter_data, body, error_message)`` for ``agent.md``."""
    md_path = agent_dir / "agent.md"
    if not md_path.exists():
        return None, None, f"agent.md が見つかりません: {md_path}"

    text = md_path.read_text(encoding="utf-8")
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", text, re.DOTALL)
    if not match:
        return None, None, "agent.md に YAML frontmatter がありません"

    try:
        data = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        return None, None, f"YAML パースエラー: {exc}"

    return data, match.group(2).strip(), None


def _check_config_agent_md_consistency(
    config: dict[str, Any], frontmatter: dict[str, Any], body: str, agent_dir: Path
) -> list[str]:
    errors: list[str] = []
    agent_name = agent_dir.name
    config_name = config.get("name", "")
    md_name = frontmatter.get("name", "")

    if config_name != md_name:
        errors.append(
            f"  [consistency:name] config.json '{config_name}' != agent.md '{md_name}'"
        )
    if config_name != agent_name:
        errors.append(
            f"  [consistency:name] config.json '{config_name}' != ディレクトリ名 '{agent_name}'"
        )

    config_desc = " ".join(config.get("description", "").split())
    md_desc = " ".join(frontmatter.get("description", "").split())
    if config_desc and md_desc and config_desc != md_desc:
        if config_desc[:20] != md_desc[:20]:
            errors.append(
                "  [consistency:description] config.json と agent.md の description が大きく異なります"
            )

    config_system = config.get("system", "")
    if not config_system:
        errors.append("  [consistency:system] config.json に system プロンプトがありません")
    elif body and body[:50] not in config_system[:100]:
        errors.append(
            "  [consistency:system] config.json の system が agent.md 本文と一致しない可能性があります"
        )

    return errors


def validate_agent_config(
    agent_dir: Path, *, check_consistency_only: bool = False
) -> tuple[bool, list[str]]:
    """Validate ``<agent_dir>/config.json`` and its consistency with ``agent.md``."""
    errors: list[str] = []

    config_path = agent_dir / "config.json"
    if not config_path.exists():
        return False, [f"  config.json が見つかりません: {config_path}"]

    try:
        with config_path.open(encoding="utf-8") as f:
            config = json.load(f)
    except json.JSONDecodeError as exc:
        return False, [f"  JSON パースエラー: {exc}"]

    if not check_consistency_only:
        try:
            ManagedAgentConfig.model_validate(config)
        except ValidationError as exc:
            errors.extend(
                f"  [schema:{loc}] {msg}".replace("[schema:(root)]", "[schema:]")
                for loc, msg in (
                    (
                        ".".join(str(x) for x in err.get("loc", ())) or "(root)",
                        err.get("msg", ""),
                    )
                    for err in exc.errors()
                )
            )

    frontmatter, body, md_error = _extract_agent_md(agent_dir)
    if md_error:
        errors.append(f"  [agent.md] {md_error}")
    elif frontmatter is not None and body is not None:
        errors.extend(_check_config_agent_md_consistency(config, frontmatter, body, agent_dir))

    return len(errors) == 0, errors


# ── Bundle validation ───────────────────────────────────────────────────────


def load_manifest() -> dict[str, Any]:
    """Load ``.manifest.json`` (or return an empty manifest if absent)."""
    if MANIFEST_PATH.exists():
        with MANIFEST_PATH.open(encoding="utf-8") as f:
            return json.load(f)
    return {"version": 1, "agents": {}}


def _validate_agent_ref(
    bundle_name: str,
    role: str,
    agent: dict[str, Any],
    manifest: dict[str, Any],
) -> list[str]:
    """Validate one ``task_agent`` / ``qa_agent`` block."""
    errors: list[str] = []
    agent_name = agent["name"]
    agent_ref = agent["ref"]
    agent_dir = REPO_ROOT / agent_ref

    ref_tail = agent_ref.rsplit("/", 1)[-1]
    if ref_tail != agent_name:
        errors.append(
            f"{bundle_name}: {role} の ref 末尾 ({ref_tail}) が name ({agent_name}) と一致しません"
        )

    if not agent_dir.exists():
        errors.append(f"{bundle_name}: {role} ディレクトリが存在しません: {agent_ref}")
    else:
        if not (agent_dir / "agent.md").exists():
            errors.append(
                f"{bundle_name}: {role} の agent.md が見つかりません: {agent_ref}/agent.md"
            )
        if not (agent_dir / "config.json").exists():
            errors.append(
                f"{bundle_name}: {role} の config.json が見つかりません: {agent_ref}/config.json"
            )

    if agent_name not in manifest.get("agents", {}):
        errors.append(f"{bundle_name}: {role} ({agent_name}) がマニフェストに未登録です")

    return errors


def validate_bundle_dir(bundle_dir: Path, manifest: dict[str, Any]) -> list[str]:
    """Validate one bundle directory. Returns the list of error messages."""
    errors: list[str] = []
    bundle_name = bundle_dir.name

    bundle_json_path = bundle_dir / "bundle.json"
    if not bundle_json_path.exists():
        return [f"{bundle_name}: bundle.json が見つかりません"]

    try:
        with bundle_json_path.open(encoding="utf-8") as f:
            raw = json.load(f)
    except json.JSONDecodeError as exc:
        return [f"{bundle_name}: bundle.json の JSON パースエラー: {exc}"]

    try:
        bundle = Bundle.model_validate(raw)
    except ValidationError as exc:
        first = exc.errors()[0]
        loc = ".".join(str(x) for x in first.get("loc", ())) or "(root)"
        return [f"{bundle_name}: スキーマ検証エラー: [{loc}] {first.get('msg', '')}"]

    if bundle.name != bundle_name:
        errors.append(
            f"{bundle_name}: bundle.json の name ({bundle.name}) が "
            f"ディレクトリ名 ({bundle_name}) と一致しません"
        )

    errors.extend(
        _validate_agent_ref(bundle_name, "Task Agent", raw["task_agent"], manifest)
    )
    errors.extend(
        _validate_agent_ref(bundle_name, "QA Agent", raw["qa_agent"], manifest)
    )

    if bundle.task_agent.name == bundle.qa_agent.name:
        errors.append(
            f"{bundle_name}: Task Agent と QA Agent が同一です ({bundle.task_agent.name})。"
            "Actor-Critic パターンでは別エージェントである必要があります"
        )

    if bundle.skill:
        full_skill_path = REPO_ROOT / bundle.skill
        if not full_skill_path.exists():
            errors.append(f"{bundle_name}: SKILL ファイルが見つかりません: {bundle.skill}")

    qa = bundle.workflow.qa
    if qa.convergence_delta >= qa.pass_threshold:
        errors.append(
            f"{bundle_name}: convergence_delta ({qa.convergence_delta}) が "
            f"pass_threshold ({qa.pass_threshold}) 以上です。"
            "収束判定が意図通りに動作しない可能性があります"
        )

    return errors


def find_bundle_dirs(target: str | Path | None = None) -> list[Path]:
    """Return the list of bundle directories to validate.

    ``target`` is either ``None`` (meaning *all* bundles) or a path-like
    pointing to a specific bundle directory (relative paths resolve against
    the repo root).
    """
    if target is not None:
        target_path = Path(target)
        if not target_path.is_absolute():
            target_path = REPO_ROOT / target_path
        if not target_path.is_dir():
            raise FileNotFoundError(f"ディレクトリが見つかりません: {target}")
        return [target_path]

    if not BUNDLES_DIR.exists():
        return []

    return [
        d
        for d in sorted(BUNDLES_DIR.iterdir())
        if d.is_dir() and not d.name.startswith(".")
    ]


# ── Convenience: iterate all subagent directories ───────────────────────────


def find_subagent_targets() -> list[Path]:
    """Return every ``agents/agents/<name>/agent.md`` path (sorted)."""
    if not SUBAGENTS_DIR.exists():
        return []
    targets = sorted(SUBAGENTS_DIR.glob("*/agent.md"))
    targets.extend(sorted(SUBAGENTS_DIR.glob("*.md")))
    return targets


def find_agent_config_dirs() -> list[Path]:
    """Return every directory under ``agents/agents`` that contains ``config.json``."""
    if not SUBAGENTS_DIR.exists():
        return []
    return sorted(
        d
        for d in SUBAGENTS_DIR.iterdir()
        if d.is_dir() and (d / "config.json").exists()
    )


__all__ = [
    "FRONTMATTER_RE",
    "KNOWN_FRONTMATTER_FIELDS",
    "extract_frontmatter",
    "find_agent_config_dirs",
    "find_bundle_dirs",
    "find_subagent_targets",
    "load_manifest",
    "validate_agent_config",
    "validate_bundle_dir",
    "validate_subagent_frontmatter",
]
