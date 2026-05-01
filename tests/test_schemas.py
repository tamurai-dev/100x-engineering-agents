"""Tests for src/duo_agents/schemas.py — pydantic v2 models.

These tests cover:

* Required-field enforcement
* Field-level constraints (regex, min/max length, value enums)
* Cross-field invariants (tools XOR disallowedTools, convergence_delta < pass_threshold)
* additionalProperties: false enforcement
* Bundle / ManagedAgentConfig structural validation
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from duo_agents.schemas import (  # noqa: E402
    AgentRef,
    Bundle,
    BundleQA,
    ManagedAgentConfig,
    SubagentFrontmatter,
)

FIXTURES = REPO_ROOT / "tests" / "fixtures"
BUNDLES_VALID = FIXTURES / "bundles" / "valid"
BUNDLES_INVALID = FIXTURES / "bundles" / "invalid"


# ── SubagentFrontmatter ──────────────────────────────────────────────────────


class TestSubagentFrontmatter:
    def test_minimal_passes(self):
        fm = SubagentFrontmatter(name="foo", description="A normal description here.")
        assert fm.name == "foo"

    def test_name_pattern_rejects_uppercase(self):
        with pytest.raises(ValidationError, match="should match pattern"):
            SubagentFrontmatter(name="Foo-Bar", description="A description.")

    def test_name_pattern_rejects_trailing_hyphen(self):
        with pytest.raises(ValidationError, match="should match pattern"):
            SubagentFrontmatter(name="foo-", description="A description.")

    def test_description_min_length(self):
        with pytest.raises(ValidationError, match="at least 10"):
            SubagentFrontmatter(name="foo", description="short")

    def test_tools_disallowed_tools_exclusive(self):
        with pytest.raises(ValidationError, match="排他"):
            SubagentFrontmatter(
                name="foo",
                description="A description goes here.",
                tools=["Read"],
                disallowedTools=["Bash"],
            )

    def test_unknown_field_rejected(self):
        with pytest.raises(ValidationError, match="Extra inputs"):
            SubagentFrontmatter.model_validate(
                {"name": "foo", "description": "A description.", "bogus": 1}
            )

    def test_model_alias_accepted(self):
        for tier in ("haiku", "sonnet", "opus", "inherit"):
            fm = SubagentFrontmatter(name="foo", description="A description.", model=tier)
            assert fm.model == tier

    def test_model_full_id_accepted(self):
        fm = SubagentFrontmatter(
            name="foo", description="A description.", model="claude-haiku-4-5"
        )
        assert fm.model == "claude-haiku-4-5"

    def test_model_invalid_value_rejected(self):
        with pytest.raises(ValidationError):
            SubagentFrontmatter(name="foo", description="A description.", model="gpt-4")

    def test_effort_enum(self):
        with pytest.raises(ValidationError, match="Input should be"):
            SubagentFrontmatter(name="foo", description="A description.", effort="weird")

    def test_color_enum(self):
        for color in ("red", "blue", "green", "yellow", "purple", "orange", "pink", "cyan"):
            SubagentFrontmatter(name="foo", description="A description.", color=color)
        with pytest.raises(ValidationError):
            SubagentFrontmatter(name="foo", description="A description.", color="black")


# ── ManagedAgentConfig ───────────────────────────────────────────────────────


class TestManagedAgentConfig:
    def test_real_configs_validate(self):
        agents_dir = REPO_ROOT / "agents" / "agents"
        for config_path in sorted(agents_dir.glob("*/config.json")):
            with config_path.open() as f:
                ManagedAgentConfig.model_validate(json.load(f))

    def test_required_fields_enforced(self):
        with pytest.raises(ValidationError, match="Field required"):
            ManagedAgentConfig.model_validate({"name": "foo", "system": "p"})

    def test_unknown_model_rejected(self):
        with pytest.raises(ValidationError, match="unknown model id"):
            ManagedAgentConfig.model_validate(
                {
                    "name": "foo",
                    "model": "claude-opus-99-99",
                    "system": "system prompt",
                }
            )

    def test_metadata_caps(self):
        with pytest.raises(ValidationError, match="at most 16"):
            ManagedAgentConfig.model_validate(
                {
                    "name": "foo",
                    "model": "claude-haiku-4-5",
                    "system": "p",
                    "metadata": {f"k{i}": "v" for i in range(17)},
                }
            )


# ── Bundle ───────────────────────────────────────────────────────────────────


class TestBundle:
    def test_real_bundle_validates(self):
        for bundle_path in (REPO_ROOT / "agents" / "bundles").glob("*/bundle.json"):
            with bundle_path.open() as f:
                Bundle.model_validate(json.load(f))

    def test_minimal_fixture(self):
        with (BUNDLES_VALID / "minimal-bundle.json").open() as f:
            Bundle.model_validate(json.load(f))

    def test_full_fixture(self):
        with (BUNDLES_VALID / "full-bundle.json").open() as f:
            Bundle.model_validate(json.load(f))

    def test_bundle_name_must_end_with_bundle(self):
        with pytest.raises(ValidationError, match="should match pattern"):
            self._build_bundle(name="my-cool-thing")

    def test_artifact_format_must_be_known(self):
        with pytest.raises(ValidationError, match="artifact_format"):
            self._build_bundle(artifact_format="bogus")

    def test_invalid_fixtures_all_fail(self):
        for fixture in BUNDLES_INVALID.glob("*.json"):
            with fixture.open() as f:
                data = json.load(f)
            with pytest.raises(ValidationError):
                Bundle.model_validate(data)

    @staticmethod
    def _build_bundle(**overrides):
        base = {
            "name": "code-review-bundle",
            "version": "1.0.0",
            "description": "Test bundle for unit tests.",
            "artifact_format": "text",
            "task_agent": {
                "name": "code-reviewer",
                "ref": "agents/agents/code-reviewer",
            },
            "qa_agent": {
                "name": "code-review-qa",
                "ref": "agents/agents/code-review-qa",
            },
            "workflow": {"qa": {"max_iterations": 3, "pass_threshold": 0.80}},
        }
        base.update(overrides)
        return Bundle.model_validate(base)


class TestBundleQA:
    def test_defaults(self):
        qa = BundleQA(max_iterations=3, pass_threshold=0.8)
        assert qa.convergence_delta == 0.02
        assert qa.escalation_threshold == 0.40
        assert qa.model_escalation == ["haiku", "sonnet"]

    def test_iterations_in_range(self):
        with pytest.raises(ValidationError):
            BundleQA(max_iterations=0, pass_threshold=0.8)
        with pytest.raises(ValidationError):
            BundleQA(max_iterations=11, pass_threshold=0.8)

    def test_threshold_in_unit_interval(self):
        with pytest.raises(ValidationError):
            BundleQA(max_iterations=3, pass_threshold=1.5)

    def test_model_escalation_unique(self):
        with pytest.raises(ValidationError, match="unique"):
            BundleQA(
                max_iterations=3,
                pass_threshold=0.8,
                model_escalation=["haiku", "haiku"],
            )


# ── AgentRef ────────────────────────────────────────────────────────────────


class TestAgentRef:
    def test_valid_ref(self):
        AgentRef(name="my-agent", ref="agents/agents/my-agent")

    def test_invalid_ref_path(self):
        with pytest.raises(ValidationError, match="should match pattern"):
            AgentRef(name="my-agent", ref="other/path/my-agent")

    def test_invalid_name(self):
        with pytest.raises(ValidationError, match="should match pattern"):
            AgentRef(name="My-Agent", ref="agents/agents/my-agent")
