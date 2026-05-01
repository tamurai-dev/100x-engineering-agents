#!/usr/bin/env python3
"""
QA 戦略エンジン テストスイート

テスト対象:
  - artifact_format → QAStrategy 解決
  - テンプレートファイルの存在確認
  - 戦略マッピングの完全性
  - エッジケース（不正な artifact_format）
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

# scripts/ を sys.path に追加
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from duet_factory.qa_strategy import (
    TEMPLATES_DIR,
    VALID_ARTIFACT_FORMATS,
    QAStrategy,
    get_strategy_summary,
    list_strategies,
    resolve_qa_strategy,
)


class TestResolveQAStrategy(unittest.TestCase):
    """resolve_qa_strategy() のテスト。"""

    def test_presentation_returns_dedicated_template(self) -> None:
        strategy = resolve_qa_strategy("presentation")
        self.assertEqual(strategy.artifact_format, "presentation")
        self.assertEqual(strategy.agent_template, "qa-presentation.md.tmpl")
        self.assertEqual(strategy.config_template, "qa-config.json.tmpl")
        self.assertIn("convert_pdf", strategy.pipeline)
        self.assertIn("vision_qa", strategy.pipeline)
        self.assertEqual(strategy.execution_strategy, "script_generation")

    def test_html_ui_returns_dedicated_template(self) -> None:
        strategy = resolve_qa_strategy("html_ui")
        self.assertEqual(strategy.artifact_format, "html_ui")
        self.assertEqual(strategy.agent_template, "qa-html-ui.md.tmpl")
        self.assertIn("playwright_screenshot", strategy.pipeline)
        self.assertEqual(strategy.execution_strategy, "script_generation")

    def test_code_returns_dedicated_template(self) -> None:
        strategy = resolve_qa_strategy("code")
        self.assertEqual(strategy.artifact_format, "code")
        self.assertEqual(strategy.agent_template, "qa-code.md.tmpl")
        self.assertIn("lint", strategy.pipeline)
        self.assertIn("test_execution", strategy.pipeline)
        self.assertEqual(strategy.execution_strategy, "direct")

    def test_text_returns_generic_template(self) -> None:
        strategy = resolve_qa_strategy("text")
        self.assertEqual(strategy.artifact_format, "text")
        self.assertEqual(strategy.agent_template, "qa-generic.md.tmpl")

    def test_document_returns_generic_template(self) -> None:
        strategy = resolve_qa_strategy("document")
        self.assertEqual(strategy.artifact_format, "document")
        self.assertEqual(strategy.agent_template, "qa-generic.md.tmpl")

    def test_structured_data_returns_generic_template(self) -> None:
        strategy = resolve_qa_strategy("structured_data")
        self.assertEqual(strategy.artifact_format, "structured_data")

    def test_media_image_returns_generic_template(self) -> None:
        strategy = resolve_qa_strategy("media_image")
        self.assertEqual(strategy.artifact_format, "media_image")

    def test_media_video_returns_generic_template(self) -> None:
        strategy = resolve_qa_strategy("media_video")
        self.assertEqual(strategy.artifact_format, "media_video")

    def test_environment_state_returns_generic_template(self) -> None:
        strategy = resolve_qa_strategy("environment_state")
        self.assertEqual(strategy.artifact_format, "environment_state")

    def test_invalid_format_raises_value_error(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            resolve_qa_strategy("invalid_format")
        self.assertIn("Unknown artifact_format", str(ctx.exception))
        self.assertIn("invalid_format", str(ctx.exception))

    def test_empty_string_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            resolve_qa_strategy("")


class TestTemplateFiles(unittest.TestCase):
    """テンプレートファイルの存在・整合性テスト。"""

    def test_all_agent_templates_exist(self) -> None:
        """全戦略の agent.md テンプレートが物理的に存在する。"""
        strategies = list_strategies()
        for fmt, strategy in strategies.items():
            path = strategy.agent_template_path
            self.assertTrue(
                path.exists(),
                f"agent template missing for {fmt}: {path}",
            )

    def test_all_config_templates_exist(self) -> None:
        """全戦略の config.json テンプレートが物理的に存在する。"""
        strategies = list_strategies()
        for fmt, strategy in strategies.items():
            path = strategy.config_template_path
            self.assertTrue(
                path.exists(),
                f"config template missing for {fmt}: {path}",
            )

    def test_validate_templates_exist_returns_empty(self) -> None:
        """validate_templates_exist() がエラーなしを返す。"""
        strategies = list_strategies()
        for fmt, strategy in strategies.items():
            errors = strategy.validate_templates_exist()
            self.assertEqual(
                errors, [], f"Template errors for {fmt}: {errors}"
            )

    def test_agent_templates_have_frontmatter(self) -> None:
        """全 agent.md テンプレートが frontmatter（---）で始まる。"""
        template_files = [
            "qa-presentation.md.tmpl",
            "qa-html-ui.md.tmpl",
            "qa-code.md.tmpl",
            "qa-generic.md.tmpl",
        ]
        for tmpl in template_files:
            path = TEMPLATES_DIR / tmpl
            content = path.read_text(encoding="utf-8")
            self.assertTrue(
                content.startswith("---"),
                f"{tmpl} does not start with frontmatter delimiter",
            )

    def test_config_template_is_valid_json(self) -> None:
        """qa-config.json.tmpl が有効な JSON である。"""
        path = TEMPLATES_DIR / "qa-config.json.tmpl"
        content = path.read_text(encoding="utf-8")
        data = json.loads(content)
        self.assertIn("name", data)
        self.assertIn("model", data)
        self.assertIn("system", data)
        self.assertIn("tools", data)

    def test_config_template_has_qa_system_prompt(self) -> None:
        """qa-config.json.tmpl の system に QA 専門家プロンプトが含まれる。"""
        path = TEMPLATES_DIR / "qa-config.json.tmpl"
        data = json.loads(path.read_text(encoding="utf-8"))
        system = data["system"]
        self.assertIn("品質検査専門家", system)
        # fresh-context concept expressed in Japanese
        self.assertIn("タスク実行の過程を知らない状態", system)

    def test_config_template_has_placeholders(self) -> None:
        """qa-config.json.tmpl がプレースホルダーを含む。"""
        path = TEMPLATES_DIR / "qa-config.json.tmpl"
        data = json.loads(path.read_text(encoding="utf-8"))
        # Duet Factory がこれらを実際の値に置換する
        self.assertEqual(data["name"], "<duet-name>-qa")
        self.assertEqual(data["model"], "<model>")


class TestQAStrategyCompleteness(unittest.TestCase):
    """QA 戦略マッピングの完全性テスト。"""

    def test_all_schema_formats_are_covered(self) -> None:
        """duo_agents.config.artifacts.VALID_ARTIFACT_FORMATS が単一情報源として
        qa_strategy.VALID_ARTIFACT_FORMATS と一致していることを確認する。

        PR-2 で JSON Schema を pydantic に置換したため、artifact_format の権威は
        ``src/duo_agents/config/artifacts.py`` にある。
        """
        sys.path.insert(0, str(REPO_ROOT / "src"))
        from duo_agents.config.artifacts import VALID_ARTIFACT_FORMATS as CONFIG_FORMATS

        self.assertEqual(
            CONFIG_FORMATS,
            VALID_ARTIFACT_FORMATS,
            "qa_strategy.VALID_ARTIFACT_FORMATS does not match duo_agents.config.artifacts",
        )

    def test_every_format_resolves_without_error(self) -> None:
        """全 artifact_format が resolve_qa_strategy() でエラーなく解決される。"""
        for fmt in VALID_ARTIFACT_FORMATS:
            strategy = resolve_qa_strategy(fmt)
            self.assertIsInstance(strategy, QAStrategy)
            self.assertTrue(len(strategy.agent_template) > 0)
            self.assertTrue(len(strategy.config_template) > 0)

    def test_dedicated_formats_have_specific_templates(self) -> None:
        """専用テンプレートを持つ format が正しいテンプレートを返す。"""
        dedicated = {
            "presentation": "qa-presentation.md.tmpl",
            "html_ui": "qa-html-ui.md.tmpl",
            "code": "qa-code.md.tmpl",
        }
        for fmt, expected_tmpl in dedicated.items():
            strategy = resolve_qa_strategy(fmt)
            self.assertEqual(
                strategy.agent_template,
                expected_tmpl,
                f"{fmt} should use {expected_tmpl}",
            )

    def test_non_dedicated_formats_use_generic(self) -> None:
        """専用テンプレートがない format は generic を使用する。"""
        generic_formats = [
            "text",
            "structured_data",
            "document",
            "media_image",
            "media_video",
            "environment_state",
        ]
        for fmt in generic_formats:
            strategy = resolve_qa_strategy(fmt)
            self.assertEqual(
                strategy.agent_template,
                "qa-generic.md.tmpl",
                f"{fmt} should use qa-generic.md.tmpl",
            )

    def test_generic_preserves_original_artifact_format(self) -> None:
        """generic fallback が元の artifact_format を保持する。"""
        for fmt in ["text", "document", "structured_data"]:
            strategy = resolve_qa_strategy(fmt)
            self.assertEqual(
                strategy.artifact_format,
                fmt,
                f"generic strategy for {fmt} should preserve artifact_format",
            )

    def test_round_trip_resolve(self) -> None:
        """resolve → artifact_format → 再 resolve がエラーなく動作する。"""
        for fmt in VALID_ARTIFACT_FORMATS:
            strategy = resolve_qa_strategy(fmt)
            # round-trip: artifact_format should be valid for re-resolve
            strategy2 = resolve_qa_strategy(strategy.artifact_format)
            self.assertEqual(strategy.agent_template, strategy2.agent_template)


class TestQAStrategyProperties(unittest.TestCase):
    """QAStrategy データクラスのプロパティテスト。"""

    def test_strategy_is_frozen(self) -> None:
        """QAStrategy は immutable（frozen=True）。"""
        strategy = resolve_qa_strategy("code")
        with self.assertRaises(AttributeError):
            strategy.artifact_format = "text"  # type: ignore[misc]

    def test_agent_template_path_is_absolute(self) -> None:
        """agent_template_path が絶対パスを返す。"""
        strategy = resolve_qa_strategy("code")
        self.assertTrue(strategy.agent_template_path.is_absolute())

    def test_config_template_path_is_absolute(self) -> None:
        """config_template_path が絶対パスを返す。"""
        strategy = resolve_qa_strategy("code")
        self.assertTrue(strategy.config_template_path.is_absolute())


class TestListStrategies(unittest.TestCase):
    """list_strategies() / get_strategy_summary() のテスト。"""

    def test_list_strategies_returns_all_formats(self) -> None:
        """list_strategies() が全 artifact_format を返す。"""
        strategies = list_strategies()
        self.assertEqual(set(strategies.keys()), VALID_ARTIFACT_FORMATS)

    def test_get_strategy_summary_returns_string(self) -> None:
        """get_strategy_summary() が文字列を返す。"""
        summary = get_strategy_summary()
        self.assertIsInstance(summary, str)
        self.assertIn("presentation", summary)
        self.assertIn("code", summary)
        self.assertIn("generic", summary)


# ── main ──────────────────────────────────────────────────────

def main() -> None:
    """テスト実行のエントリポイント。"""
    print("=" * 60)
    print("QA 戦略エンジン テストスイート")
    print("=" * 60)
    print()

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    test_classes = [
        TestResolveQAStrategy,
        TestTemplateFiles,
        TestQAStrategyCompleteness,
        TestQAStrategyProperties,
        TestListStrategies,
    ]

    for cls in test_classes:
        suite.addTests(loader.loadTestsFromTestCase(cls))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print()
    total = result.testsRun
    failures = len(result.failures) + len(result.errors)
    print(f"Results: {total} tests, {total - failures} passed, {failures} failed")

    if not result.wasSuccessful():
        sys.exit(1)


if __name__ == "__main__":
    main()
