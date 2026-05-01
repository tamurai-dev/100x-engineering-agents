#!/usr/bin/env python3
"""
Bundle Factory テストスイート

bundle-factory.py / bundle_factory/ モジュールのユニットテスト。
API 呼び出しなしで検証可能なロジックのみテストする。

テスト対象:
  - Bundle Blueprint バリデーション
  - QA Agent テンプレート展開
  - Task Agent ファイル生成
  - bundle.json 生成
  - workflow.md 生成
  - 共通ユーティリティ（parse_json_lenient, extract_json）
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from duo_agents.json_utils import extract_json, parse_json_lenient
from bundle_factory.bundle_blueprint import (
    _validate_bundle_blueprint,
    expand_qa_agent,
    expand_task_agent,
    generate_bundle_json,
    generate_workflow_md,
)
from bundle_factory.qa_strategy import VALID_ARTIFACT_FORMATS, resolve_qa_strategy


# ── テスト用 Blueprint フィクスチャ ───────────────────

def _make_blueprint(
    bundle_name: str = "test-bundle",
    task_agent_name: str = "test-task",
    description: str = "テスト用バンドルの説明文です。50文字以上になるように記述しています。",
    agent_type: str = "generation_subjective",
    artifact_format: str = "presentation",
    task_system_prompt: str = "あなたはテスト専門家です。\n\n## 責務\n1. テスト実行\n\n## 出力形式\nJSON\n\n## 制約事項\n- テスト以外しない",
    task_tools: list | None = None,
    skill_topics: list | None = None,
) -> dict:
    return {
        "bundle_name": bundle_name,
        "task_agent_name": task_agent_name,
        "description": description,
        "agent_type": agent_type,
        "artifact_format": artifact_format,
        "task_system_prompt": task_system_prompt,
        "task_tools": task_tools or ["bash", "read", "glob", "grep", "write"],
        "task_disallowed_tools": [],
        "skill_topics": skill_topics or ["スライド生成", "pptxgenjs"],
        "test_prompts": [
            {
                "name": "基本テスト",
                "prompt": "テスト実行してください",
                "expected_behaviors": ["テスト完了"],
                "success_criteria": "エラーなし",
            }
        ],
    }


class TestBundleBlueprintValidation(unittest.TestCase):
    """Bundle Blueprint バリデーションのテスト。"""

    def test_valid_blueprint_passes(self) -> None:
        bp = _make_blueprint()
        _validate_bundle_blueprint(bp)  # should not raise

    def test_missing_required_field_raises(self) -> None:
        bp = _make_blueprint()
        del bp["bundle_name"]
        with self.assertRaises(ValueError) as ctx:
            _validate_bundle_blueprint(bp)
        self.assertIn("bundle_name", str(ctx.exception))

    def test_invalid_agent_type_raises(self) -> None:
        bp = _make_blueprint(agent_type="invalid_type")
        with self.assertRaises(ValueError) as ctx:
            _validate_bundle_blueprint(bp)
        self.assertIn("agent_type", str(ctx.exception))

    def test_invalid_artifact_format_raises(self) -> None:
        bp = _make_blueprint(artifact_format="invalid_format")
        with self.assertRaises(ValueError) as ctx:
            _validate_bundle_blueprint(bp)
        self.assertIn("artifact_format", str(ctx.exception))

    def test_bundle_name_must_end_with_bundle(self) -> None:
        bp = _make_blueprint(bundle_name="test-agent")
        with self.assertRaises(ValueError) as ctx:
            _validate_bundle_blueprint(bp)
        self.assertIn("-bundle", str(ctx.exception))

    def test_bundle_name_must_be_kebab_case(self) -> None:
        bp = _make_blueprint(bundle_name="TestBundle-bundle")
        with self.assertRaises(ValueError) as ctx:
            _validate_bundle_blueprint(bp)
        self.assertIn("kebab-case", str(ctx.exception))

    def test_all_valid_agent_types(self) -> None:
        valid_types = [
            "detection", "generation_verifiable", "generation_subjective",
            "repair_transform", "planning", "research_retrieval",
            "classification", "extraction",
        ]
        for t in valid_types:
            bp = _make_blueprint(agent_type=t)
            _validate_bundle_blueprint(bp)

    def test_all_valid_artifact_formats(self) -> None:
        for fmt in VALID_ARTIFACT_FORMATS:
            bp = _make_blueprint(artifact_format=fmt)
            _validate_bundle_blueprint(bp)


class TestExpandTaskAgent(unittest.TestCase):
    """Task Agent ファイル生成のテスト。"""

    def test_agent_md_contains_name(self) -> None:
        bp = _make_blueprint()
        agent_md, _, _ = expand_task_agent(bp)
        self.assertIn("name: test-task", agent_md)

    def test_agent_md_contains_system_prompt(self) -> None:
        bp = _make_blueprint()
        agent_md, _, _ = expand_task_agent(bp)
        self.assertIn("あなたはテスト専門家です", agent_md)

    def test_config_json_structure(self) -> None:
        bp = _make_blueprint()
        _, config, _ = expand_task_agent(bp)
        self.assertEqual(config["name"], "test-task")
        self.assertIn("system", config)
        self.assertIn("tools", config)
        self.assertEqual(config["model"], "claude-sonnet-4-6")

    def test_test_prompts_included(self) -> None:
        bp = _make_blueprint()
        _, _, prompts = expand_task_agent(bp)
        self.assertEqual(len(prompts), 1)
        self.assertEqual(prompts[0]["name"], "基本テスト")

    def test_tools_in_agent_md(self) -> None:
        bp = _make_blueprint()
        agent_md, _, _ = expand_task_agent(bp)
        self.assertIn("tools:", agent_md)
        self.assertIn("Bash", agent_md)
        self.assertIn("Read", agent_md)

    def test_disallowed_tools(self) -> None:
        bp = _make_blueprint()
        bp["task_disallowed_tools"] = ["write", "edit"]
        bp["task_tools"] = ["bash", "read"]
        agent_md, _, _ = expand_task_agent(bp)
        self.assertIn("disallowedTools:", agent_md)
        self.assertIn("Write", agent_md)


class TestExpandQAAgent(unittest.TestCase):
    """QA Agent テンプレート展開のテスト。"""

    def test_presentation_qa_uses_sonnet(self) -> None:
        bp = _make_blueprint(artifact_format="presentation")
        _, config = expand_qa_agent(bp)
        self.assertEqual(config["model"], "claude-sonnet-4-6")

    def test_code_qa_uses_haiku(self) -> None:
        bp = _make_blueprint(
            bundle_name="code-test-bundle",
            artifact_format="code",
        )
        _, config = expand_qa_agent(bp)
        self.assertEqual(config["model"], "claude-haiku-4-5")

    def test_qa_agent_md_from_template(self) -> None:
        bp = _make_blueprint(artifact_format="presentation")
        agent_md, _ = expand_qa_agent(bp)
        self.assertIn("品質検査", agent_md)
        self.assertIn("fresh-context", agent_md)

    def test_qa_config_has_tools(self) -> None:
        bp = _make_blueprint()
        _, config = expand_qa_agent(bp)
        self.assertIn("tools", config)
        tool_configs = config["tools"][0]["configs"]
        tool_names = [t["name"] for t in tool_configs]
        self.assertIn("bash", tool_names)
        self.assertIn("read", tool_names)

    def test_all_artifact_formats_produce_qa_agent(self) -> None:
        for fmt in VALID_ARTIFACT_FORMATS:
            bp = _make_blueprint(
                bundle_name=f"{fmt}-test-bundle",
                artifact_format=fmt,
            )
            agent_md, config = expand_qa_agent(bp)
            self.assertTrue(len(agent_md) > 100, f"{fmt} agent_md too short")
            self.assertIn("name", config)

    def test_placeholder_replacement(self) -> None:
        bp = _make_blueprint(
            bundle_name="slide-gen-bundle",
            description="スライドを生成するバンドル",
            artifact_format="presentation",
        )
        agent_md, config = expand_qa_agent(bp)
        # Placeholders should be replaced
        self.assertNotIn("<bundle-name>", agent_md)
        self.assertNotIn("<bundle-description>", agent_md)
        self.assertNotIn("<model>", json.dumps(config))


class TestGenerateBundleJson(unittest.TestCase):
    """bundle.json 生成のテスト。"""

    def test_basic_structure(self) -> None:
        bp = _make_blueprint()
        bj = generate_bundle_json(bp)
        self.assertEqual(bj["name"], "test-bundle")
        self.assertEqual(bj["version"], "1.0.0")
        self.assertEqual(bj["artifact_format"], "presentation")

    def test_agent_refs(self) -> None:
        bp = _make_blueprint()
        bj = generate_bundle_json(bp)
        self.assertEqual(bj["task_agent"]["name"], "test-task")
        self.assertEqual(bj["task_agent"]["ref"], "agents/agents/test-task")
        self.assertEqual(bj["qa_agent"]["name"], "test-qa")
        self.assertEqual(bj["qa_agent"]["ref"], "agents/agents/test-qa")

    def test_workflow_qa_config(self) -> None:
        bp = _make_blueprint()
        bj = generate_bundle_json(bp)
        qa = bj["workflow"]["qa"]
        self.assertEqual(qa["max_iterations"], 3)
        self.assertEqual(qa["pass_threshold"], 0.80)
        self.assertEqual(qa["convergence_delta"], 0.02)
        self.assertTrue(qa["keep_best"])

    def test_execution_strategy_from_qa_strategy(self) -> None:
        bp = _make_blueprint(artifact_format="presentation")
        bj = generate_bundle_json(bp)
        self.assertEqual(bj["workflow"]["execution"]["strategy"], "script_generation")

        bp2 = _make_blueprint(
            bundle_name="code-test-bundle",
            artifact_format="code",
        )
        bj2 = generate_bundle_json(bp2)
        self.assertEqual(bj2["workflow"]["execution"]["strategy"], "direct")

    def test_metadata_has_timestamp(self) -> None:
        bp = _make_blueprint()
        bj = generate_bundle_json(bp)
        self.assertIn("metadata", bj)
        self.assertIn("created_at", bj["metadata"])
        self.assertEqual(bj["metadata"]["author"], "bundle-factory")

    def test_skill_path(self) -> None:
        bp = _make_blueprint()
        bj = generate_bundle_json(bp)
        self.assertEqual(bj["skill"], "agents/bundles/test-bundle/skill.md")


class TestGenerateWorkflowMd(unittest.TestCase):
    """workflow.md 生成のテスト。"""

    def test_workflow_contains_bundle_name(self) -> None:
        bp = _make_blueprint()
        bj = generate_bundle_json(bp)
        wf = generate_workflow_md(bp, bj)
        self.assertIn("test-bundle", wf)

    def test_workflow_contains_phases(self) -> None:
        bp = _make_blueprint()
        bj = generate_bundle_json(bp)
        wf = generate_workflow_md(bp, bj)
        self.assertIn("Phase A:", wf)
        self.assertIn("Phase B:", wf)
        self.assertIn("Phase C:", wf)
        self.assertIn("Phase D:", wf)

    def test_workflow_contains_agent_names(self) -> None:
        bp = _make_blueprint()
        bj = generate_bundle_json(bp)
        wf = generate_workflow_md(bp, bj)
        self.assertIn("test-task", wf)
        self.assertIn("test-qa", wf)


class TestSharedUtils(unittest.TestCase):
    """共通ユーティリティのテスト。"""

    def test_extract_json_from_code_block(self) -> None:
        text = 'Some text\n```json\n{"key": "value"}\n```\nMore text'
        result = extract_json(text)
        self.assertEqual(json.loads(result), {"key": "value"})

    def test_extract_json_bare(self) -> None:
        text = 'prefix {"key": "value"} suffix'
        result = extract_json(text)
        self.assertEqual(json.loads(result), {"key": "value"})

    def test_extract_json_raises_on_no_json(self) -> None:
        with self.assertRaises(ValueError):
            extract_json("no json here")

    def test_parse_json_lenient_normal(self) -> None:
        result = parse_json_lenient('{"key": "value"}')
        self.assertEqual(result, {"key": "value"})

    def test_parse_json_lenient_trailing_comma(self) -> None:
        result = parse_json_lenient('{"key": "value",}')
        self.assertEqual(result, {"key": "value"})

    def test_parse_json_lenient_truncated(self) -> None:
        result = parse_json_lenient('{"key": "value"')
        self.assertEqual(result, {"key": "value"})

    def test_parse_json_lenient_nested_trailing(self) -> None:
        result = parse_json_lenient('{"arr": [1, 2, 3,]}')
        self.assertEqual(result, {"arr": [1, 2, 3]})


class TestBundleFactoryCLI(unittest.TestCase):
    """bundle-factory.py CLI のドライランテスト。"""

    def test_dry_run_does_not_require_api_key(self) -> None:
        """--dry-run は API キー不要で実行できる。"""
        import subprocess

        result = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "scripts" / "bundle-factory.py"),
                "--spec", "テスト用仕様",
                "--dry-run",
            ],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")
        self.assertIn("DRY RUN", result.stdout)

    def test_dry_run_with_format(self) -> None:
        """--dry-run --format でテンプレート情報が表示される。"""
        import subprocess

        result = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "scripts" / "bundle-factory.py"),
                "--spec", "テスト仕様",
                "--dry-run",
                "--format", "presentation",
            ],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")
        self.assertIn("qa-presentation.md.tmpl", result.stdout)
        self.assertIn("sonnet", result.stdout)


if __name__ == "__main__":
    # Run tests with summary
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    total = result.testsRun
    failures = len(result.failures) + len(result.errors)
    passed = total - failures
    print(f"\nResults: {total} tests, {passed} passed, {failures} failed")

    sys.exit(0 if result.wasSuccessful() else 1)
