#!/usr/bin/env python3
"""
validate-bundle.py の自動テスト

各テストケースが期待通り PASS/FAIL するかを検証する。

Usage:
    python -m pytest tests/test_validate_bundle.py -v
    python tests/test_validate_bundle.py  # pytest なしでも実行可能
"""

import json
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from pathlib import Path as _Path
import importlib.util

# validate-bundle.py をハイフン付きファイル名なので動的インポート
_spec = importlib.util.spec_from_file_location(
    "validate_bundle",
    REPO_ROOT / "scripts" / "validate-bundle.py",
)
validate_bundle_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(validate_bundle_mod)

load_schema = validate_bundle_mod.load_schema
load_manifest = validate_bundle_mod.load_manifest
validate_bundle = validate_bundle_mod.validate_bundle
_validate_agent_ref = validate_bundle_mod._validate_agent_ref

FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "bundles"
VALID_DIR = FIXTURES_DIR / "valid"
INVALID_DIR = FIXTURES_DIR / "invalid"


def _schema_only_validate(fixture_path: Path) -> list[str]:
    """フィクスチャファイルをスキーマのみで検証する（ファイルシステムチェックなし）。"""
    import jsonschema

    schema = load_schema()
    errors: list[str] = []

    with open(fixture_path, encoding="utf-8") as f:
        bundle = json.load(f)

    try:
        jsonschema.validate(bundle, schema)
    except jsonschema.ValidationError as e:
        errors.append(e.message)

    return errors


def _full_validate(fixture_name: str) -> list[str]:
    """実際のバンドルディレクトリに対して完全バリデーションを実行する。"""
    schema = load_schema()
    manifest = load_manifest()
    bundle_dir = REPO_ROOT / "agents" / "bundles" / fixture_name
    return validate_bundle(bundle_dir, schema, manifest)


class TestResults:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []

    def assert_pass(self, name: str, errors: list[str]):
        if not errors:
            print(f"  PASS: {name}")
            self.passed += 1
        else:
            print(f"  FAIL: {name} — expected PASS but got errors:")
            for e in errors:
                print(f"    - {e}")
            self.failed += 1
            self.errors.append(name)

    def assert_fail(self, name: str, errors: list[str]):
        if errors:
            print(f"  PASS: {name}")
            self.passed += 1
        else:
            print(f"  FAIL: {name} — expected FAIL but passed")
            self.failed += 1
            self.errors.append(name)

    def summary(self):
        total = self.passed + self.failed
        print()
        print(f"============================================================")
        print(f"結果: {self.passed} passed / {self.failed} failed / {total} total")
        print(f"============================================================")
        return self.failed == 0


def main():
    results = TestResults()

    print(f"Bundle バリデーション テストスイート")
    print(f"Schema: agents/schemas/bundle.schema.json")
    print(f"============================================================")
    print()

    # ── 正常系: スキーマのみ ──
    print("[正常系] スキーマバリデーション PASS が期待されるケース")
    for fixture in sorted(VALID_DIR.glob("*.json")):
        errors = _schema_only_validate(fixture)
        results.assert_pass(f"スキーマ: {fixture.stem}", errors)

    print()

    # ── 異常系: スキーマのみ ──
    print("[異常系] スキーマバリデーション FAIL が期待されるケース")
    for fixture in sorted(INVALID_DIR.glob("*.json")):
        errors = _schema_only_validate(fixture)
        results.assert_fail(f"スキーマ: {fixture.stem}", errors)

    print()

    # ── 正常系: 実バンドル完全バリデーション ──
    print("[実バンドル] agents/bundles/*/bundle.json の完全検証")
    full_errors = _full_validate("code-review-bundle")
    results.assert_pass("完全検証: code-review-bundle", full_errors)

    print()

    # ── ref 整合性テスト ──
    print("[整合性] ref パスと name の一貫性チェック")
    manifest = load_manifest()

    # ref 末尾が name と一致するケース
    agent_ok = {"name": "code-reviewer", "ref": "agents/agents/code-reviewer"}
    ref_errors_ok = _validate_agent_ref("test-bundle", "Task Agent", agent_ok, manifest)
    results.assert_pass("ref一貫性: 一致", ref_errors_ok)

    # ref 末尾が name と不一致のケース
    agent_bad = {"name": "wrong-name", "ref": "agents/agents/code-reviewer"}
    ref_errors_bad = _validate_agent_ref("test-bundle", "Task Agent", agent_bad, manifest)
    has_ref_error = any("ref 末尾" in e for e in ref_errors_bad)
    if has_ref_error:
        results.assert_fail("ref一貫性: 不一致検出", ref_errors_bad)
    else:
        print(f"  FAIL: ref一貫性: 不一致検出 — ref 不一致エラーが検出されませんでした")
        results.failed += 1
        results.errors.append("ref一貫性: 不一致検出")

    print()

    # ── config.json 存在チェックテスト ──
    print("[整合性] config.json 存在チェック")
    # 存在するエージェント
    agent_exists = {"name": "code-reviewer", "ref": "agents/agents/code-reviewer"}
    config_errors = _validate_agent_ref("test-bundle", "Task Agent", agent_exists, manifest)
    has_config_error = any("config.json" in e for e in config_errors)
    if not has_config_error:
        results.assert_pass("config.json: 存在確認", [])
    else:
        results.assert_pass("config.json: 存在確認", config_errors)

    # 存在しないエージェント
    agent_missing = {"name": "nonexistent-agent", "ref": "agents/agents/nonexistent-agent"}
    missing_errors = _validate_agent_ref("test-bundle", "Task Agent", agent_missing, manifest)
    has_dir_error = any("ディレクトリが存在しません" in e for e in missing_errors)
    if has_dir_error:
        results.assert_fail("config.json: 存在しないエージェント検出", missing_errors)
    else:
        print(f"  FAIL: config.json: 存在しないエージェント検出 — ディレクトリ不存在エラーが未検出")
        results.failed += 1
        results.errors.append("config.json: 存在しないエージェント検出")

    print()

    # ── 同一エージェントチェック（スキーマでは検出不可、バリデーターの論理チェック） ──
    print("[論理] Task Agent / QA Agent 同一性チェック")
    same_agent_bundle = {
        "name": "same-agent-bundle",
        "version": "1.0.0",
        "description": "Task Agent と QA Agent が同一のバンドル。Actor-Critic パターン違反。",
        "artifact_format": "text",
        "task_agent": {"name": "code-reviewer", "ref": "agents/agents/code-reviewer"},
        "qa_agent": {"name": "code-reviewer", "ref": "agents/agents/code-reviewer"},
        "workflow": {"qa": {"max_iterations": 3, "pass_threshold": 0.80}}
    }
    with tempfile.TemporaryDirectory() as tmpdir:
        bundle_dir = Path(tmpdir) / "same-agent-bundle"
        bundle_dir.mkdir()
        with open(bundle_dir / "bundle.json", "w") as f:
            json.dump(same_agent_bundle, f)
        schema = load_schema()
        same_errors = validate_bundle(bundle_dir, schema, manifest)
        has_same_error = any("同一です" in e for e in same_errors)
        if has_same_error:
            results.assert_fail("同一エージェント検出", same_errors)
        else:
            print(f"  FAIL: 同一エージェント検出 — 同一性エラーが未検出")
            results.failed += 1
            results.errors.append("同一エージェント検出")

    print()

    # ── QA 設定論理チェック ──
    print("[論理] QA 設定の整合性チェック")

    # convergence_delta >= pass_threshold のケース
    bad_qa_bundle = {
        "name": "bad-qa-bundle",
        "version": "1.0.0",
        "description": "convergence_delta が pass_threshold 以上のバンドル。",
        "artifact_format": "text",
        "task_agent": {"name": "code-reviewer", "ref": "agents/agents/code-reviewer"},
        "qa_agent": {"name": "code-review-qa", "ref": "agents/agents/code-review-qa"},
        "workflow": {
            "qa": {
                "max_iterations": 3,
                "pass_threshold": 0.05,
                "convergence_delta": 0.10
            }
        }
    }
    with tempfile.TemporaryDirectory() as tmpdir:
        bundle_dir = Path(tmpdir) / "bad-qa-bundle"
        bundle_dir.mkdir()
        with open(bundle_dir / "bundle.json", "w") as f:
            json.dump(bad_qa_bundle, f)

        schema = load_schema()
        qa_errors = validate_bundle(bundle_dir, schema, manifest)
        has_qa_error = any("convergence_delta" in e for e in qa_errors)
        if has_qa_error:
            results.assert_fail("QA論理: delta >= threshold 検出", qa_errors)
        else:
            print(f"  FAIL: QA論理: delta >= threshold 検出 — 論理エラーが未検出")
            results.failed += 1
            results.errors.append("QA論理: delta >= threshold 検出")

    success = results.summary()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
