#!/usr/bin/env python3
"""
Managed Agents config.json バリデーター

config.json を managed-agent-config.schema.json で検証し、
agent.md との整合性もチェックする。

Usage:
    python scripts/validate-config.py                         # 全エージェント検証
    python scripts/validate-config.py agents/agents/code-reviewer  # 個別検証
    python scripts/validate-config.py --check-consistency     # agent.md との整合性のみ
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML が必要です。 pip install pyyaml を実行してください。")
    sys.exit(2)

try:
    import jsonschema
except ImportError:
    print("ERROR: jsonschema が必要です。 pip install jsonschema を実行してください。")
    sys.exit(2)


REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = REPO_ROOT / "agents" / "schemas" / "managed-agent-config.schema.json"
AGENTS_DIR = REPO_ROOT / "agents" / "agents"

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)", re.DOTALL)


def load_schema() -> dict:
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        return json.load(f)


def load_config(agent_dir: Path) -> tuple[dict | None, str | None]:
    config_path = agent_dir / "config.json"
    if not config_path.exists():
        return None, f"config.json が見つかりません: {config_path}"
    try:
        with open(config_path, encoding="utf-8") as f:
            return json.load(f), None
    except json.JSONDecodeError as e:
        return None, f"JSON パースエラー: {e}"


def extract_agent_md(agent_dir: Path) -> tuple[dict | None, str | None, str | None]:
    """agent.md から frontmatter と本文を抽出する。"""
    md_path = agent_dir / "agent.md"
    if not md_path.exists():
        return None, None, f"agent.md が見つかりません: {md_path}"

    text = md_path.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(text)
    if not match:
        return None, None, "agent.md に YAML frontmatter がありません"

    try:
        data = yaml.safe_load(match.group(1))
    except yaml.YAMLError as e:
        return None, None, f"YAML パースエラー: {e}"

    body = match.group(2).strip()
    return data, body, None


def validate_config_schema(config: dict, schema: dict) -> list[str]:
    """config.json を JSON Schema で検証する。"""
    errors = []
    validator = jsonschema.Draft202012Validator(schema)
    for error in sorted(validator.iter_errors(config), key=lambda e: list(e.path)):
        path = ".".join(str(p) for p in error.absolute_path) or "(root)"
        errors.append(f"  [schema:{path}] {error.message}")
    return errors


def check_consistency(config: dict, frontmatter: dict, body: str, agent_dir: Path) -> list[str]:
    """config.json と agent.md の整合性をチェックする。"""
    errors = []
    agent_name = agent_dir.name

    # name の一致
    config_name = config.get("name", "")
    md_name = frontmatter.get("name", "")
    if config_name != md_name:
        errors.append(f"  [consistency:name] config.json '{config_name}' != agent.md '{md_name}'")

    if config_name != agent_name:
        errors.append(f"  [consistency:name] config.json '{config_name}' != ディレクトリ名 '{agent_name}'")

    # description の一致（正規化して比較）
    config_desc = " ".join(config.get("description", "").split())
    md_desc = " ".join(frontmatter.get("description", "").split())
    if config_desc and md_desc and config_desc != md_desc:
        # 完全一致は求めず、先頭20文字が一致すれば OK（フォーマット差異を許容）
        if config_desc[:20] != md_desc[:20]:
            errors.append(f"  [consistency:description] config.json と agent.md の description が大きく異なります")

    # system プロンプトの存在チェック
    config_system = config.get("system", "")
    if not config_system:
        errors.append("  [consistency:system] config.json に system プロンプトがありません")
    elif body and body[:50] not in config_system[:100]:
        # 本文の冒頭部分が system に含まれているかチェック
        errors.append("  [consistency:system] config.json の system が agent.md 本文と一致しない可能性があります")

    return errors


def validate_agent(agent_dir: Path, schema: dict, check_consistency_only: bool = False) -> tuple[bool, list[str]]:
    """1エージェントを検証する。"""
    errors = []

    # config.json の検証
    config, config_error = load_config(agent_dir)
    if config_error:
        return False, [f"  {config_error}"]

    if not check_consistency_only:
        schema_errors = validate_config_schema(config, schema)
        errors.extend(schema_errors)

    # agent.md との整合性チェック
    frontmatter, body, md_error = extract_agent_md(agent_dir)
    if md_error:
        errors.append(f"  [agent.md] {md_error}")
    elif frontmatter is not None and body is not None:
        consistency_errors = check_consistency(config, frontmatter, body, agent_dir)
        errors.extend(consistency_errors)

    return len(errors) == 0, errors


def main():
    check_only = "--check-consistency" in sys.argv
    explicit_dirs = [a for a in sys.argv[1:] if not a.startswith("--")]

    schema = load_schema()

    if explicit_dirs:
        agent_dirs = [Path(d) for d in explicit_dirs]
    else:
        agent_dirs = sorted(
            d for d in AGENTS_DIR.iterdir()
            if d.is_dir() and (d / "config.json").exists()
        )

    if not agent_dirs:
        print("検証対象のエージェントが見つかりません")
        sys.exit(1)

    passed = 0
    failed = 0

    for agent_dir in agent_dirs:
        agent_dir = Path(agent_dir).resolve()
        name = agent_dir.name
        success, errors = validate_agent(agent_dir, schema, check_only)

        if success:
            print(f"  PASS: {name}")
            passed += 1
        else:
            print(f"  FAIL: {name}")
            for err in errors:
                print(err)
            failed += 1

    print(f"\n{'='*40}")
    print(f"  {passed} passed / {failed} failed / {passed + failed} total")
    print(f"{'='*40}")
    sys.exit(1 if failed > 0 else 0)


if __name__ == "__main__":
    main()
