#!/usr/bin/env python3
"""
validate_subagents.py の自動テスト

各テストケースが期待通り PASS/FAIL するかを検証する。
macOS / Windows / Linux いずれでも動作する（パス操作に pathlib を使用）。

Usage:
    python -m pytest tests/test_validate_subagents.py -v
    python tests/test_validate_subagents.py  # pytest なしでも実行可能
"""

import json
import sys
from pathlib import Path

# プロジェクトルートを sys.path に追加
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from validate_subagents import extract_frontmatter, validate_frontmatter, load_schema, FRONTMATTER_RE

FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"


def get_schema():
    return load_schema()


def run_validation(filename: str) -> tuple[bool, list[str]]:
    """フィクスチャファイルを検証し、(success, errors) を返す。"""
    filepath = FIXTURES_DIR / filename
    schema = get_schema()

    data, parse_error = extract_frontmatter(filepath)
    if parse_error:
        return False, [parse_error]

    errors = validate_frontmatter(data, schema, filepath)
    return len(errors) == 0, errors


class TestResults:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []

    def assert_pass(self, name: str, filename: str):
        success, errors = run_validation(filename)
        if success:
            self.passed += 1
            print(f"  PASS: {name}")
        else:
            self.failed += 1
            self.errors.append((name, errors))
            print(f"  FAIL: {name} (expected PASS)")
            for e in errors:
                print(f"        {e}")

    def assert_fail(self, name: str, filename: str, expected_keyword: str = ""):
        success, errors = run_validation(filename)
        if not success:
            if expected_keyword and not any(expected_keyword in e for e in errors):
                self.failed += 1
                self.errors.append((name, [f"Expected error containing '{expected_keyword}' not found"]))
                print(f"  FAIL: {name} (wrong error type)")
                for e in errors:
                    print(f"        {e}")
            else:
                self.passed += 1
                print(f"  PASS: {name}")
        else:
            self.failed += 1
            self.errors.append((name, ["Expected FAIL but got PASS"]))
            print(f"  FAIL: {name} (expected FAIL but got PASS)")


def main():
    print("=" * 60)
    print("Subagent Validator テストスイート")
    print("=" * 60)
    print(f"Python: {sys.version}")
    print(f"Platform: {sys.platform}")
    print(f"Fixtures: {FIXTURES_DIR}")
    print()

    r = TestResults()

    # === 正常系 ===
    print("[正常系] バリデーション PASS が期待されるケース:")
    r.assert_pass("必須フィールドのみ", "valid-minimal.md")
    r.assert_pass("全フィールド指定", "valid-full.md")
    print()

    # === 異常系 ===
    print("[異常系] バリデーション FAIL が期待されるケース:")
    r.assert_fail("name 欠落", "invalid-missing-name.md", "'name' is a required property")
    r.assert_fail("description 欠落", "invalid-missing-description.md", "'description' is a required property")
    r.assert_fail("name フォーマット不正", "invalid-bad-name.md", "does not match")
    r.assert_fail("tools/disallowedTools 排他違反", "invalid-tools-conflict.md", "排他")
    r.assert_fail("不正な model 値", "invalid-bad-model.md")
    r.assert_fail("不正な effort 値", "invalid-bad-effort.md", "is not one of")
    r.assert_fail("未知フィールド", "invalid-unknown-field.md", "Additional properties")
    r.assert_fail("frontmatter なし", "invalid-no-frontmatter.md", "YAML frontmatter")
    r.assert_fail("description が短すぎる", "invalid-short-description.md", "too short")
    r.assert_fail("本文（body）が空", "invalid-empty-body.md", "body")
    print()

    # === 既存エージェント ===
    print("[既存エージェント] agents/agents/*/agent.md の検証:")
    agents_dir = REPO_ROOT / "agents" / "agents"
    for filepath in sorted(agents_dir.glob("*/agent.md")):
        schema = get_schema()
        data, parse_error = extract_frontmatter(filepath)
        if parse_error:
            r.failed += 1
            print(f"  FAIL: {filepath.parent.name} — {parse_error}")
            continue
        errs = validate_frontmatter(data, schema, filepath)
        if errs:
            r.failed += 1
            print(f"  FAIL: {filepath.parent.name}")
            for e in errs:
                print(f"        {e}")
        else:
            r.passed += 1
            print(f"  PASS: {filepath.parent.name}")

    # === 結果 ===
    print()
    print("=" * 60)
    total = r.passed + r.failed
    print(f"結果: {r.passed} passed / {r.failed} failed / {total} total")
    print("=" * 60)

    if r.failed > 0:
        print("\n失敗したテスト:")
        for name, errors in r.errors:
            print(f"  - {name}")
            for e in errors:
                print(f"    {e}")

    return 0 if r.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
