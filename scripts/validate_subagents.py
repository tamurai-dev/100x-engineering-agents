#!/usr/bin/env python3
"""Claude Code Subagent Frontmatter Validator (thin shim).

Delegates the actual validation logic to :mod:`duo_agents.validators` /
:mod:`duo_agents.schemas`. This module only handles CLI argument parsing,
output formatting and report generation.

Usage:
    python scripts/validate_subagents.py                    # 全 agent.md を検証
    python scripts/validate_subagents.py path/to/agent.md   # 個別ファイル検証
    python scripts/validate_subagents.py --check-template   # テンプレート整合性検証
"""

from __future__ import annotations

import datetime
import json
import platform
import sys
from pathlib import Path

# Make ``duo_agents`` importable when called via ``python scripts/...`` without
# ``pip install -e .`` having been run.
REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src"
if SRC_DIR.exists() and str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from duo_agents.config.paths import SUBAGENTS_DIR  # noqa: E402
from duo_agents.validators import (  # noqa: E402
    FRONTMATTER_RE,
    KNOWN_FRONTMATTER_FIELDS as KNOWN_FIELDS,
    extract_frontmatter,
    find_subagent_targets,
    validate_subagent_frontmatter,
)

# Backwards-compatible re-exports for tests/test_validate_subagents.py.
__all__ = [
    "FRONTMATTER_RE",
    "KNOWN_FIELDS",
    "extract_frontmatter",
    "load_schema",
    "validate_frontmatter",
    "validate_file",
]


def load_schema() -> dict:
    """Legacy compatibility shim — pydantic now owns the schema.

    Returns an empty dict so that callers passing it to
    :func:`validate_frontmatter` remain compatible.
    """
    return {}


def validate_frontmatter(data: dict, schema: dict, filepath: Path) -> list[str]:
    """Validate frontmatter ``data`` and return error messages."""
    return validate_subagent_frontmatter(data, filepath)


def validate_file(filepath: Path, schema: dict) -> tuple[bool, list[str]]:
    """Validate a single file. Returns ``(success, messages)``."""
    data, parse_error = extract_frontmatter(filepath)
    if parse_error:
        return False, [f"  {parse_error}"]
    errors = validate_frontmatter(data, schema, filepath)
    return len(errors) == 0, errors


def _check_template() -> int:
    print("テンプレートスキーマ整合性チェック...")
    tmpl_path = REPO_ROOT / "agents" / "templates" / "subagent.md.tmpl"
    if not tmpl_path.exists():
        print(f"FAIL: テンプレートが見つかりません: {tmpl_path}")
        return 1
    data, err = extract_frontmatter(tmpl_path)
    if err:
        print(f"FAIL: {err}")
        return 1
    unknown = set(data.keys()) - KNOWN_FIELDS
    if unknown:
        print(f"WARN: テンプレートに未知のフィールド: {', '.join(sorted(unknown))}")
    print(f"OK: テンプレートの frontmatter フィールドは有効です（{len(data)} フィールド）")
    return 0


def _generate_report(results: list[dict], report_path: str) -> None:
    report = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "python_version": platform.python_version(),
        "platform": platform.system(),
        "schema": "src/duo_agents/schemas.py::SubagentFrontmatter",
        "summary": {
            "total": len(results),
            "passed": sum(1 for r in results if r["status"] == "PASS"),
            "failed": sum(1 for r in results if r["status"] == "FAIL"),
        },
        "results": results,
    }
    out = Path(report_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)


def main() -> None:
    args = sys.argv[1:]
    if "--check-template" in args:
        sys.exit(_check_template())

    explicit_files: list[str] = []
    report_path: str | None = None
    i = 0
    while i < len(args):
        if args[i] == "--report" and i + 1 < len(args):
            report_path = args[i + 1]
            i += 2
        elif args[i].startswith("--"):
            i += 1
        else:
            explicit_files.append(args[i])
            i += 1

    if explicit_files:
        targets = [Path(f) for f in explicit_files]
    else:
        targets = find_subagent_targets()
        if not SUBAGENTS_DIR.exists():
            print(f"ERROR: ディレクトリが見つかりません: {SUBAGENTS_DIR}")
            sys.exit(2)

    if not targets:
        print("検証対象のファイルがありません。")
        sys.exit(0)

    print("Claude Code Subagent Frontmatter Validator")
    print("Schema: src/duo_agents/schemas.py::SubagentFrontmatter")
    print(f"対象: {len(targets)} ファイル")
    print("=" * 60)

    passed = failed = 0
    results: list[dict] = []
    for filepath in targets:
        if not filepath.exists():
            print(f"\nFAIL: {filepath}")
            print("  ファイルが見つかりません")
            failed += 1
            results.append({"file": str(filepath), "status": "FAIL", "errors": ["ファイルが見つかりません"]})
            continue

        rel = filepath.relative_to(REPO_ROOT) if filepath.is_relative_to(REPO_ROOT) else filepath
        success, messages = validate_file(filepath, {})
        if success:
            print(f"\nPASS: {rel}")
            passed += 1
            results.append({"file": str(rel), "status": "PASS", "errors": []})
        else:
            print(f"\nFAIL: {rel}")
            for msg in messages:
                print(msg)
            failed += 1
            results.append({"file": str(rel), "status": "FAIL", "errors": [m.strip() for m in messages]})

    print("\n" + "=" * 60)
    print(f"結果: {passed} passed / {failed} failed / {len(targets)} total")

    if report_path:
        _generate_report(results, report_path)
        print(f"レポート: {report_path}")

    sys.exit(1 if failed > 0 else 0)


if __name__ == "__main__":
    main()
