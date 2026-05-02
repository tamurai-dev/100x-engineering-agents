#!/usr/bin/env python3
"""
Duet ワークフロー実行エンジン テストスイート

run-duet.py の関数群のユニットテスト。
API 呼び出しなしで検証可能なロジックのみテストする。

テスト対象:
  - parse_qa_result: QA JSON パース（正常系 + 異常系）
  - build_skill_preamble: SKILL.md プロンプト前文生成
  - build_feedback_history: フィードバック蓄積テキスト生成
  - load_duet: duet.json 読み込み
  - load_agent_config: config.json 読み込み
  - load_skill_md: SKILL.md 読み込み
  - run_duet (dry-run): ワークフロー検証モード
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
from run_duet_helpers import (
    DEFAULT_ESCALATION_THRESHOLD,
    DEFAULT_MODEL_ESCALATION,
    ESCALATION_IMPROVEMENT_DELTA,
    EVIDENCE_RESPONSE_LIMIT,
    FILE_OUTPUT_INSTRUCTIONS,
    FORMAT_REQUIRES_SONNET,
    MULTIAGENT_BETA,
    ORCHESTRATOR_MAX_QA_PROMPT_CHARS,
    build_feedback_history,
    build_orchestrator_system,
    build_skill_preamble,
    list_session_output_files,
    load_duet,
    load_agent_config,
    load_skill_md,
    parse_qa_result,
    should_escalate_model,
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


class TestLoadDuet(unittest.TestCase):
    """duet.json 読み込みのテスト。"""

    def test_load_existing_duet(self):
        """既存の code-review-duet が正しく読み込まれる。"""
        duet = load_duet("code-review-duet")
        self.assertEqual(duet["name"], "code-review-duet")
        self.assertIn("task_agent", duet)
        self.assertIn("qa_agent", duet)
        self.assertIn("workflow", duet)

    def test_load_nonexistent_duet_exits(self):
        """存在しないデュエットは sys.exit する。"""
        with self.assertRaises(SystemExit):
            load_duet("nonexistent-duet-xyz")


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
        """SKILL.md がないデュエットは None を返す。"""
        result = load_skill_md("code-review-duet")
        # code-review-duet has no skill.md
        self.assertIsNone(result)

    def test_load_existing_skill(self):
        """SKILL.md があるデュエットは内容を返す。"""
        # Create a temporary skill.md for testing
        duet_dir = REPO_ROOT / "agents" / "duets" / "code-review-duet"
        skill_path = duet_dir / "skill.md"
        try:
            skill_path.write_text("# Test Skill\ntest content", encoding="utf-8")
            result = load_skill_md("code-review-duet")
            self.assertIsNotNone(result)
            self.assertIn("Test Skill", result)
        finally:
            if skill_path.exists():
                skill_path.unlink()


class TestDryRun(unittest.TestCase):
    """ドライランモードのテスト。"""

    def test_dry_run_returns_ok(self):
        """ドライランは API を呼ばずに検証結果を返す。"""
        from run_duet_helpers import run_duet

        result = run_duet(
            duet_name="code-review-duet",
            user_input="",
            dry_run=True,
        )
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["status"], "ok")

    def test_dry_run_with_model_override(self):
        """ドライランはモデルオーバーライドでもクラッシュしない。"""
        from run_duet_helpers import run_duet

        result = run_duet(
            duet_name="code-review-duet",
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


class TestModelEscalation(unittest.TestCase):
    """モデル自動エスカレーションのテスト。"""

    def test_escalate_when_score_below_threshold(self):
        """スコアが閾値以下で改善なしの場合、エスカレーションする。"""
        result = should_escalate_model(
            current_model="haiku",
            score=0.15,
            prev_score=None,
            escalation_order=["haiku", "sonnet"],
            threshold=0.40,
        )
        self.assertEqual(result, "sonnet")

    def test_no_escalate_when_score_above_threshold(self):
        """スコアが閾値以上の場合、エスカレーションしない。"""
        result = should_escalate_model(
            current_model="haiku",
            score=0.50,
            prev_score=None,
            escalation_order=["haiku", "sonnet"],
            threshold=0.40,
        )
        self.assertIsNone(result)

    def test_no_escalate_when_improving(self):
        """スコアが改善している場合、閾値以下でもエスカレーションしない。"""
        result = should_escalate_model(
            current_model="haiku",
            score=0.30,
            prev_score=0.10,
            escalation_order=["haiku", "sonnet"],
            threshold=0.40,
        )
        self.assertIsNone(result)

    def test_escalate_when_not_improving_enough(self):
        """改善幅が不十分な場合、エスカレーションする。"""
        result = should_escalate_model(
            current_model="haiku",
            score=0.12,
            prev_score=0.10,
            escalation_order=["haiku", "sonnet"],
            threshold=0.40,
        )
        self.assertEqual(result, "sonnet")

    def test_no_escalate_already_at_top(self):
        """最上位モデルの場合、エスカレーションしない。"""
        result = should_escalate_model(
            current_model="sonnet",
            score=0.10,
            prev_score=None,
            escalation_order=["haiku", "sonnet"],
            threshold=0.40,
        )
        self.assertIsNone(result)

    def test_escalate_with_three_models(self):
        """3段階エスカレーション（haiku→sonnet→opus）。"""
        result = should_escalate_model(
            current_model="sonnet",
            score=0.10,
            prev_score=None,
            escalation_order=["haiku", "sonnet", "opus"],
            threshold=0.40,
        )
        self.assertEqual(result, "opus")

    def test_no_escalate_unknown_model(self):
        """不明なモデルの場合、エスカレーションしない。"""
        result = should_escalate_model(
            current_model="unknown",
            score=0.10,
            prev_score=None,
            escalation_order=["haiku", "sonnet"],
            threshold=0.40,
        )
        self.assertIsNone(result)

    def test_escalation_constants(self):
        """エスカレーション定数が合理的な値。"""
        self.assertEqual(DEFAULT_MODEL_ESCALATION, ["haiku", "sonnet"])
        self.assertGreater(DEFAULT_ESCALATION_THRESHOLD, 0.0)
        self.assertLess(DEFAULT_ESCALATION_THRESHOLD, 1.0)
        self.assertGreater(ESCALATION_IMPROVEMENT_DELTA, 0.0)


class TestMultiagent(unittest.TestCase):
    """Multiagent Sessions mode tests."""

    def test_multiagent_beta_header_defined(self):
        """MULTIAGENT_BETA constant is defined."""
        self.assertIsInstance(MULTIAGENT_BETA, str)
        self.assertIn("multiagent", MULTIAGENT_BETA)

    def test_orchestrator_max_qa_prompt_chars(self):
        """ORCHESTRATOR_MAX_QA_PROMPT_CHARS is a positive integer."""
        self.assertIsInstance(ORCHESTRATOR_MAX_QA_PROMPT_CHARS, int)
        self.assertGreater(ORCHESTRATOR_MAX_QA_PROMPT_CHARS, 0)

    def test_build_orchestrator_system_basic(self):
        """build_orchestrator_system returns a non-empty string."""
        qa_settings = {
            "max_iterations": 3,
            "pass_threshold": 0.80,
            "convergence_delta": 0.02,
        }
        result = build_orchestrator_system("test-duet", qa_settings, None)
        self.assertIsInstance(result, str)
        self.assertIn("test-duet", result)
        self.assertIn("Task Agent", result)
        self.assertIn("QA Agent", result)

    def test_build_orchestrator_system_with_skill(self):
        """build_orchestrator_system includes SKILL.md when provided."""
        qa_settings = {
            "max_iterations": 3,
            "pass_threshold": 0.80,
        }
        skill = "Use pptxgenjs to generate slides."
        result = build_orchestrator_system("test-duet", qa_settings, skill)
        self.assertIn("SKILL.md", result)
        self.assertIn("pptxgenjs", result)

    def test_build_orchestrator_system_truncates_long_skill(self):
        """build_orchestrator_system truncates very long SKILL.md."""
        qa_settings = {
            "max_iterations": 3,
            "pass_threshold": 0.80,
        }
        long_skill = "x" * (ORCHESTRATOR_MAX_QA_PROMPT_CHARS + 1000)
        result = build_orchestrator_system("test-duet", qa_settings, long_skill)
        # The skill content should be truncated
        self.assertLessEqual(
            result.count("x"), ORCHESTRATOR_MAX_QA_PROMPT_CHARS + 10
        )

    def test_build_orchestrator_system_contains_workflow_params(self):
        """build_orchestrator_system includes workflow parameters."""
        qa_settings = {
            "max_iterations": 5,
            "pass_threshold": 0.90,
            "convergence_delta": 0.03,
            "escalation_threshold": 0.35,
        }
        result = build_orchestrator_system("test-duet", qa_settings, None)
        self.assertIn("0.9", result)
        self.assertIn("5", result)
        self.assertIn("0.35", result)

    def test_build_orchestrator_system_shared_filesystem(self):
        """build_orchestrator_system mentions shared filesystem."""
        qa_settings = {
            "max_iterations": 3,
            "pass_threshold": 0.80,
        }
        result = build_orchestrator_system("test-duet", qa_settings, None)
        self.assertIn("filesystem", result.lower())
        self.assertIn("/mnt/session/outputs/", result)

    def test_build_orchestrator_system_json_block(self):
        """build_orchestrator_system includes JSON output format."""
        qa_settings = {
            "max_iterations": 3,
            "pass_threshold": 0.80,
        }
        result = build_orchestrator_system("test-duet", qa_settings, None)
        self.assertIn("final_status", result)
        self.assertIn("best_score", result)


class TestFileOutputInstructions(unittest.TestCase):
    """File output instructions and format-based model defaults."""

    def test_file_output_instructions_defined(self):
        """FILE_OUTPUT_INSTRUCTIONS is a non-empty string."""
        self.assertIsInstance(FILE_OUTPUT_INSTRUCTIONS, str)
        self.assertIn("/mnt/session/outputs/", FILE_OUTPUT_INSTRUCTIONS)
        self.assertIn("ls -la", FILE_OUTPUT_INSTRUCTIONS)

    def test_file_output_instructions_contains_verification(self):
        """Instructions include file verification step."""
        self.assertIn("verify", FILE_OUTPUT_INSTRUCTIONS.lower())

    def test_format_requires_sonnet_defined(self):
        """FORMAT_REQUIRES_SONNET is a set of known formats."""
        self.assertIsInstance(FORMAT_REQUIRES_SONNET, set)
        self.assertIn("presentation", FORMAT_REQUIRES_SONNET)
        self.assertIn("structured_data", FORMAT_REQUIRES_SONNET)
        self.assertIn("media_image", FORMAT_REQUIRES_SONNET)

    def test_format_requires_sonnet_excludes_text(self):
        """Text-based formats should not require sonnet."""
        self.assertNotIn("text", FORMAT_REQUIRES_SONNET)
        self.assertNotIn("code", FORMAT_REQUIRES_SONNET)

    def test_build_skill_preamble_with_file_instructions(self):
        """Skill preamble and file instructions combine correctly."""
        preamble = build_skill_preamble("Use pptxgenjs for slides.")
        combined = preamble + "Create slides" + FILE_OUTPUT_INSTRUCTIONS
        self.assertIn("SKILL.md", combined)
        self.assertIn("/mnt/session/outputs/", combined)
        self.assertIn("Create slides", combined)


if __name__ == "__main__":
    unittest.main()
