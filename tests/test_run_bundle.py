#!/usr/bin/env python3
"""
Bundle ワークフロー実行エンジン テストスイート

run-bundle.py の関数群のユニットテスト。
API 呼び出しなしで検証可能なロジックのみテストする。

テスト対象:
  - parse_qa_result: QA JSON パース（正常系 + 異常系）
  - build_skill_preamble: SKILL.md プロンプト前文生成
  - build_feedback_history: フィードバック蓄積テキスト生成
  - load_bundle: bundle.json 読み込み
  - load_agent_config: config.json 読み込み
  - load_skill_md: SKILL.md 読み込み
  - run_bundle (dry-run): ワークフロー検証モード
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

# Import target module functions
from run_bundle_helpers import (
    EVIDENCE_RESPONSE_LIMIT,
    build_feedback_history,
    build_skill_preamble,
    list_session_output_files,
    load_bundle,
    load_agent_config,
    load_skill_md,
    parse_qa_result,
)


class TestParseQaResult(unittest.TestCase):
    """QA Agent レスポンスパーサーのテスト。"""

    def test_valid_json_block(self):
        """```json ブロックから正しくパースできる。"""
        response = (
            "検査結果です:\n\n"
            "```json\n"
            '{"score": 0.85, "passed": true, '
            '"summary": "good", "findings": [], "feedback": ""}\n'
            "```\n"
        )
        result = parse_qa_result(response)
        self.assertAlmostEqual(result["score"], 0.85)
        self.assertTrue(result["passed"])
        self.assertEqual(result["summary"], "good")

    def test_valid_json_no_block(self):
        """```json ブロックなしの生 JSON もパースできる。"""
        response = '{"score": 0.70, "passed": false, "summary": "needs work", "findings": [{"type": "x"}], "feedback": "fix it"}'
        result = parse_qa_result(response)
        self.assertAlmostEqual(result["score"], 0.70)
        self.assertFalse(result["passed"])

    def test_invalid_json_returns_fallback(self):
        """JSON パース不能な場合はフォールバック結果を返す。"""
        response = "This is not JSON at all, just plain text feedback."
        result = parse_qa_result(response)
        self.assertAlmostEqual(result["score"], 0.0)
        self.assertFalse(result["passed"])
        self.assertTrue(result.get("parse_error", False))

    def test_empty_response(self):
        """空レスポンスでもクラッシュしない。"""
        result = parse_qa_result("")
        self.assertAlmostEqual(result["score"], 0.0)
        self.assertFalse(result["passed"])

    def test_json_with_trailing_text(self):
        """JSON ブロック後にテキストが続いてもパースできる。"""
        response = (
            "以下が検査結果です。\n\n"
            "```json\n"
            '{"score": 0.92, "passed": true, "summary": "excellent", '
            '"findings": [], "feedback": ""}\n'
            "```\n\n"
            "上記の通り、品質基準を満たしています。"
        )
        result = parse_qa_result(response)
        self.assertAlmostEqual(result["score"], 0.92)

    def test_json_block_without_language_tag(self):
        """言語タグなしの ``` ブロックもパースできる。"""
        response = (
            "結果:\n"
            "```\n"
            '{"score": 0.60, "passed": false, "summary": "bad", '
            '"findings": [{"type": "error"}], "feedback": "redo"}\n'
            "```"
        )
        result = parse_qa_result(response)
        self.assertAlmostEqual(result["score"], 0.60)

    def test_partial_json_in_block(self):
        """JSON ブロック内が不完全な場合フォールバックする。"""
        response = '```json\n{"score": 0.5, "passed":\n```'
        result = parse_qa_result(response)
        # Should fallback gracefully
        self.assertIn("score", result)

    def test_findings_count(self):
        """findings 配列の要素数が正しく取得できる。"""
        response = json.dumps({
            "score": 0.50,
            "passed": False,
            "summary": "issues found",
            "findings": [
                {"type": "a", "description": "x"},
                {"type": "b", "description": "y"},
                {"type": "c", "description": "z"},
            ],
            "feedback": "fix all",
        })
        result = parse_qa_result(response)
        self.assertEqual(len(result["findings"]), 3)


class TestBuildSkillPreamble(unittest.TestCase):
    """SKILL.md プロンプト前文生成のテスト。"""

    def test_basic_preamble(self):
        """基本的なスキル前文が生成される。"""
        skill = "# スライド生成スキル\n\n手順:\n1. pptxgenjs を使う"
        result = build_skill_preamble(skill)
        self.assertIn("SKILL.md", result)
        self.assertIn("スライド生成スキル", result)
        self.assertIn("pptxgenjs", result)

    def test_preamble_ends_with_separator(self):
        """前文がセパレータで終わる。"""
        result = build_skill_preamble("test content")
        self.assertIn("---", result)

    def test_empty_skill(self):
        """空のスキル内容でもクラッシュしない。"""
        result = build_skill_preamble("")
        self.assertIn("SKILL.md", result)


class TestBuildFeedbackHistory(unittest.TestCase):
    """フィードバック蓄積テキスト生成のテスト。"""

    def test_empty_history(self):
        """空の履歴は空文字を返す。"""
        result = build_feedback_history([])
        self.assertEqual(result, "")

    def test_single_entry(self):
        """1エントリの履歴が正しく整形される。"""
        entries = [
            {"iteration": 1, "score": 0.30, "feedback": "もっと詳しく"},
        ]
        result = build_feedback_history(entries)
        self.assertIn("ラウンド #1", result)
        self.assertIn("0.30", result)
        self.assertIn("もっと詳しく", result)

    def test_multiple_entries(self):
        """複数エントリの履歴が全て含まれる。"""
        entries = [
            {"iteration": 1, "score": 0.20, "feedback": "feedback 1"},
            {"iteration": 2, "score": 0.40, "feedback": "feedback 2"},
            {"iteration": 3, "score": 0.55, "feedback": "feedback 3"},
        ]
        result = build_feedback_history(entries)
        self.assertIn("ラウンド #1", result)
        self.assertIn("ラウンド #2", result)
        self.assertIn("ラウンド #3", result)
        self.assertIn("feedback 1", result)
        self.assertIn("feedback 3", result)


class TestLoadBundle(unittest.TestCase):
    """bundle.json 読み込みのテスト。"""

    def test_load_existing_bundle(self):
        """既存の code-review-bundle が正しく読み込まれる。"""
        bundle = load_bundle("code-review-bundle")
        self.assertEqual(bundle["name"], "code-review-bundle")
        self.assertIn("task_agent", bundle)
        self.assertIn("qa_agent", bundle)
        self.assertIn("workflow", bundle)

    def test_load_nonexistent_bundle_exits(self):
        """存在しないバンドルは sys.exit する。"""
        with self.assertRaises(SystemExit):
            load_bundle("nonexistent-bundle-xyz")


class TestLoadAgentConfig(unittest.TestCase):
    """config.json 読み込みのテスト。"""

    def test_load_existing_config(self):
        """既存エージェントの config.json が読み込まれる。"""
        config = load_agent_config("code-reviewer")
        self.assertEqual(config["name"], "code-reviewer")
        self.assertIn("model", config)
        self.assertIn("system", config)

    def test_load_nonexistent_config_exits(self):
        """存在しないエージェントは sys.exit する。"""
        with self.assertRaises(SystemExit):
            load_agent_config("nonexistent-agent-xyz")


class TestLoadSkillMd(unittest.TestCase):
    """SKILL.md 読み込みのテスト。"""

    def test_load_nonexistent_skill(self):
        """SKILL.md がないバンドルは None を返す。"""
        result = load_skill_md("code-review-bundle")
        # code-review-bundle has no skill.md
        self.assertIsNone(result)

    def test_load_existing_skill(self):
        """SKILL.md があるバンドルは内容を返す。"""
        # Create a temporary skill.md for testing
        bundle_dir = REPO_ROOT / "agents" / "bundles" / "code-review-bundle"
        skill_path = bundle_dir / "skill.md"
        try:
            skill_path.write_text("# Test Skill\ntest content", encoding="utf-8")
            result = load_skill_md("code-review-bundle")
            self.assertIsNotNone(result)
            self.assertIn("Test Skill", result)
        finally:
            if skill_path.exists():
                skill_path.unlink()


class TestDryRun(unittest.TestCase):
    """ドライランモードのテスト。"""

    def test_dry_run_returns_ok(self):
        """ドライランは API を呼ばずに検証結果を返す。"""
        from run_bundle_helpers import run_bundle

        result = run_bundle(
            bundle_name="code-review-bundle",
            user_input="",
            dry_run=True,
        )
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["status"], "ok")

    def test_dry_run_with_model_override(self):
        """ドライランはモデルオーバーライドでもクラッシュしない。"""
        from run_bundle_helpers import run_bundle

        result = run_bundle(
            bundle_name="code-review-bundle",
            user_input="",
            model="sonnet",
            dry_run=True,
        )
        self.assertTrue(result["dry_run"])


class TestListSessionOutputFiles(unittest.TestCase):
    """Files API セッションファイル列挙のテスト。"""

    def test_empty_on_exception(self):
        """例外時は空リストを返す。"""
        mock_client = MagicMock()
        mock_client.beta.files.list.side_effect = Exception("API error")
        result = list_session_output_files(mock_client, "test-session-id")
        self.assertEqual(result, [])

    def test_parses_file_list(self):
        """ファイルリストを正しくパースする。"""
        mock_file = MagicMock()
        mock_file.id = "file_abc123"
        mock_file.filename = "output.pptx"
        mock_file.size_bytes = 12345
        mock_file.mime_type = "application/vnd.openxmlformats-officedocument.presentationml.presentation"

        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.data = [mock_file]
        mock_client.beta.files.list.return_value = mock_result

        result = list_session_output_files(mock_client, "test-session-id")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["file_id"], "file_abc123")
        self.assertEqual(result[0]["filename"], "output.pptx")
        self.assertEqual(result[0]["size_bytes"], 12345)


class TestEvidenceResponseLimit(unittest.TestCase):
    """証跡レスポンス制限のテスト。"""

    def test_limit_is_reasonable(self):
        """制限値が合理的な範囲内。"""
        self.assertGreater(EVIDENCE_RESPONSE_LIMIT, 100)
        self.assertLessEqual(EVIDENCE_RESPONSE_LIMIT, 10000)


if __name__ == "__main__":
    unittest.main()
