#!/usr/bin/env python3
"""
Claude Code Subagent Frontmatter Validator

Claude Code v2.1+ の subagent YAML frontmatter 仕様に準拠しているか検証する。
JSON Schema (agents/schemas/subagent-frontmatter.schema.json) を使用。

Usage:
    python scripts/validate_subagents.py                    # agents/agents/*.md を全件検証
    python scripts/validate_subagents.py path/to/agent.md   # 個別ファイル検証
    python scripts/validate_subagents.py --check-template   # テンプレートのスキーマ整合性検証
"""

from __future__ import annotations

import datetime
import json
import platform
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

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
SCHEMA_PATH = REPO_ROOT / "agents" / "schemas" / "subagent-frontmatter.schema.json"
AGENTS_DIR = REPO_ROOT / "agents" / "agents"

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

# Claude Code v2.1+ 全16フィールド
KNOWN_FIELDS = {
    "name", "description", "model", "tools", "disallowedTools",
    "permissionMode", "maxTurns", "skills", "mcpServers", "hooks",
    "memory", "background", "effort", "isolation", "initialPrompt", "color",
}


def load_schema() -> dict:
    with open(SCHEMA_PATH) as f:
        return json.load(f)


def extract_frontmatter(filepath: Path) -> tuple[dict | None, str | None]:
    """Markdown ファイルから YAML frontmatter を抽出してパースする。"""
    text = filepath.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(text)
    if not match:
        return None, "YAML frontmatter が見つかりません（ファイル先頭の --- ... --- ブロック）"

    raw_yaml = match.group(1)
    # YAML コメント行を除去してからパース
    try:
        data = yaml.safe_load(raw_yaml)
    except yaml.YAMLError as e:
        return None, f"YAML パースエラー: {e}"

    if not isinstance(data, dict):
        return None, f"frontmatter がオブジェクトではありません（型: {type(data).__name__}）"

    return data, None


def validate_frontmatter(data: dict, schema: dict, filepath: Path) -> list[str]:
    """frontmatter を JSON Schema + 追加ルールで検証し、エラーリストを返す。"""
    errors = []

    # JSON Schema validation
    validator = jsonschema.Draft202012Validator(schema)
    for error in sorted(validator.iter_errors(data), key=lambda e: list(e.path)):
        path = ".".join(str(p) for p in error.absolute_path) or "(root)"
        errors.append(f"  [{path}] {error.message}")

    # Cross-field validation: tools と disallowedTools の排他チェック
    if "tools" in data and "disallowedTools" in data:
        errors.append("  [cross-field] 'tools' と 'disallowedTools' は排他です。どちらか一方のみ指定してください")

    # name がディレクトリ名と一致するか
    # 新構造: agents/agents/<name>/agent.md → name = ディレクトリ名
    # 旧構造: agents/agents/<name>.md → name = ファイル名（拡張子除く）
    if filepath.name == "agent.md":
        expected_name = filepath.parent.name
    else:
        expected_name = filepath.stem
    if "name" in data and data["name"] != expected_name:
        errors.append(
            f"  [name] frontmatter の name '{data['name']}' が '{expected_name}' と一致しません"
        )

    # 未知フィールドの警告（JSON Schema の additionalProperties: false でもカバーされるが明示的に）
    unknown = set(data.keys()) - KNOWN_FIELDS
    if unknown:
        errors.append(f"  [unknown-fields] 未知のフィールド: {', '.join(sorted(unknown))}")

    # body（frontmatter 以降）が空でないか確認
    text = filepath.read_text(encoding="utf-8")
    body = FRONTMATTER_RE.sub("", text).strip()
    if not body:
        errors.append("  [body] frontmatter 以降のシステムプロンプト（本文）が空です")

    return errors


def validate_file(filepath: Path, schema: dict) -> tuple[bool, list[str]]:
    """1ファイルを検証し、(success, messages) を返す。"""
    messages = []
    data, parse_error = extract_frontmatter(filepath)
    if parse_error:
        return False, [f"  {parse_error}"]

    errors = validate_frontmatter(data, schema, filepath)
    if errors:
        return False, errors

    return True, []


def generate_report(results: list, report_path: str) -> None:
    """バリデーション結果をJSONレポートとして保存する。"""
    report = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "python_version": platform.python_version(),
        "platform": platform.system(),
        "schema": str(SCHEMA_PATH.relative_to(REPO_ROOT)),
        "summary": {
            "total": len(results),
            "passed": sum(1 for r in results if r["status"] == "PASS"),
            "failed": sum(1 for r in results if r["status"] == "FAIL"),
        },
        "results": results,
    }

    report_file = Path(report_path)
    report_file.parent.mkdir(parents=True, exist_ok=True)
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)


def main():
    check_template = "--check-template" in sys.argv
    report_path = None
    explicit_files = []

    args = sys.argv[1:]
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

    schema = load_schema()

    if check_template:
        print("テンプレートスキーマ整合性チェック...")
        tmpl_path = REPO_ROOT / "agents" / "templates" / "subagent.md.tmpl"
        if not tmpl_path.exists():
            print(f"FAIL: テンプレートが見つかりません: {tmpl_path}")
            sys.exit(1)
        # テンプレートは意図的にプレースホルダを含むのでスキーマ検証はスキップ
        data, err = extract_frontmatter(tmpl_path)
        if err:
            print(f"FAIL: {err}")
            sys.exit(1)
        # フィールド名のみチェック（値はプレースホルダなので検証しない）
        unknown = set(data.keys()) - KNOWN_FIELDS
        if unknown:
            print(f"WARN: テンプレートに未知のフィールド: {', '.join(sorted(unknown))}")
        print(f"OK: テンプレートの frontmatter フィールドは有効です（{len(data)} フィールド）")
        return

    # 検証対象ファイルの決定
    if explicit_files:
        targets = [Path(f) for f in explicit_files]
    else:
        if not AGENTS_DIR.exists():
            print(f"ERROR: ディレクトリが見つかりません: {AGENTS_DIR}")
            sys.exit(2)
        # 新構造: agents/agents/<name>/agent.md
        # 旧構造: agents/agents/<name>.md（後方互換）
        targets = sorted(AGENTS_DIR.glob("*/agent.md"))
        targets.extend(sorted(AGENTS_DIR.glob("*.md")))

    if not targets:
        print("検証対象のファイルがありません。")
        sys.exit(0)

    total = len(targets)
    passed = 0
    failed = 0

    print(f"Claude Code Subagent Frontmatter Validator")
    print(f"Schema: {SCHEMA_PATH.relative_to(REPO_ROOT)}")
    print(f"対象: {total} ファイル")
    print("=" * 60)

    report_results = []

    for filepath in targets:
        if not filepath.exists():
            print(f"\nFAIL: {filepath}")
            print(f"  ファイルが見つかりません")
            failed += 1
            report_results.append({"file": str(filepath), "status": "FAIL", "errors": ["ファイルが見つかりません"]})
            continue

        success, messages = validate_file(filepath, schema)
        rel = filepath.relative_to(REPO_ROOT) if filepath.is_relative_to(REPO_ROOT) else filepath

        if success:
            print(f"\nPASS: {rel}")
            passed += 1
            report_results.append({"file": str(rel), "status": "PASS", "errors": []})
        else:
            print(f"\nFAIL: {rel}")
            for msg in messages:
                print(msg)
            failed += 1
            report_results.append({"file": str(rel), "status": "FAIL", "errors": [m.strip() for m in messages]})

    print("\n" + "=" * 60)
    print(f"結果: {passed} passed / {failed} failed / {total} total")

    if report_path:
        generate_report(report_results, report_path)
        print(f"レポート: {report_path}")

    sys.exit(1 if failed > 0 else 0)


if __name__ == "__main__":
    main()
