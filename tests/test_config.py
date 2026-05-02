"""Smoke tests for the ``duo_agents.config`` subpackage.

These tests verify the *internal consistency* of the configuration module.
They do NOT call the Anthropic API — that is left to the eval suite.

Goal: catch typos in model IDs / beta headers / threshold ranges before they
reach production runs.
"""

from __future__ import annotations

from pathlib import Path

from duo_agents.config import (
    AGENTS_ASSETS_DIR,
    ALL_BETAS,
    ANTHROPIC_PREBUILT_SKILLS,
    DUETS_DIR,
    DEFAULT_EDD_CONVERGENCE_DELTA,
    DEFAULT_EDD_MAX_ITERATIONS,
    DEFAULT_EDD_TARGET_OVERALL,
    DEFAULT_ESCALATION_IMPROVEMENT_DELTA,
    DEFAULT_ESCALATION_THRESHOLD,
    DEFAULT_MODEL,
    DEFAULT_QA_CONVERGENCE_DELTA,
    DEFAULT_QA_MAX_ITERATIONS,
    DEFAULT_QA_PASS_THRESHOLD,
    ESCALATION_ORDER,
    FILE_OUTPUT_INSTRUCTIONS,
    FILES_API_BETA,
    FORMAT_TO_PREBUILT,
    FORMAT_TO_QA_TEMPLATE,
    MANAGED_AGENTS_BETA,
    MANIFEST_KEY_PATH,
    MANIFEST_PATH,
    MODEL_IDS,
    MULTIAGENT_BETA,
    REPO_ROOT,
    REQUIRES_SONNET,
    SKILLS_API_BETA,
    SUBAGENTS_DIR,
    TEMPLATES_DIR,
    VALID_ARTIFACT_FORMATS,
    ModelCapabilities,
    ModelTier,
)
from duo_agents.config.models import resolve_model_id


# ── models ───────────────────────────────────────────────────────────────────


class TestModels:
    def test_every_tier_has_an_api_id(self) -> None:
        for tier in ModelTier:
            assert tier in MODEL_IDS, f"Missing API id for {tier}"
            api_id = MODEL_IDS[tier]
            assert isinstance(api_id, str)
            assert api_id.startswith("claude-"), f"Unexpected API id: {api_id}"

    def test_default_model_is_a_known_tier(self) -> None:
        assert DEFAULT_MODEL in MODEL_IDS

    def test_escalation_order_is_a_valid_permutation(self) -> None:
        assert set(ESCALATION_ORDER) == set(ModelTier)
        # haiku must be the cheapest starting point
        assert ESCALATION_ORDER[0] == ModelTier.HAIKU

    def test_resolve_model_id_accepts_tier_name(self) -> None:
        assert resolve_model_id("haiku") == MODEL_IDS[ModelTier.HAIKU]
        assert resolve_model_id("sonnet") == MODEL_IDS[ModelTier.SONNET]
        assert resolve_model_id("opus") == MODEL_IDS[ModelTier.OPUS]

    def test_resolve_model_id_passes_through_full_id(self) -> None:
        assert resolve_model_id("claude-haiku-4-5") == "claude-haiku-4-5"
        assert resolve_model_id("custom-model-name") == "custom-model-name"

    def test_capabilities_methods_exist(self) -> None:
        for tier in ModelTier:
            assert isinstance(
                ModelCapabilities.supports_legacy_thinking(tier), bool
            )
            assert isinstance(
                ModelCapabilities.supports_sampling_params(tier), bool
            )


# ── betas ────────────────────────────────────────────────────────────────────


class TestBetas:
    def test_all_betas_are_unique(self) -> None:
        assert len(ALL_BETAS) == len(set(ALL_BETAS))

    def test_all_betas_use_dated_format(self) -> None:
        # Anthropic Beta headers follow the pattern ``<feature>-YYYY-MM-DD``.
        for header in ALL_BETAS:
            parts = header.rsplit("-", 3)
            assert len(parts) == 4, f"Unexpected beta format: {header}"
            _, year, month, day = parts
            assert year.isdigit() and len(year) == 4
            assert month.isdigit() and len(month) == 2
            assert day.isdigit() and len(day) == 2

    def test_all_named_betas_are_in_all_betas(self) -> None:
        for header in (
            MANAGED_AGENTS_BETA,
            FILES_API_BETA,
            SKILLS_API_BETA,
            MULTIAGENT_BETA,
        ):
            assert header in ALL_BETAS


# ── thresholds ───────────────────────────────────────────────────────────────


class TestThresholds:
    def test_qa_thresholds_are_in_unit_interval(self) -> None:
        for value in (
            DEFAULT_QA_PASS_THRESHOLD,
            DEFAULT_QA_CONVERGENCE_DELTA,
            DEFAULT_ESCALATION_THRESHOLD,
            DEFAULT_ESCALATION_IMPROVEMENT_DELTA,
            DEFAULT_EDD_TARGET_OVERALL,
            DEFAULT_EDD_CONVERGENCE_DELTA,
        ):
            assert 0.0 <= value <= 1.0, f"Out of unit interval: {value}"

    def test_iteration_counts_are_positive(self) -> None:
        assert DEFAULT_QA_MAX_ITERATIONS > 0
        assert DEFAULT_EDD_MAX_ITERATIONS > 0

    def test_escalation_below_pass_threshold(self) -> None:
        # Conceptually escalation should kick in *before* pass.
        assert DEFAULT_ESCALATION_THRESHOLD < DEFAULT_QA_PASS_THRESHOLD


# ── paths ────────────────────────────────────────────────────────────────────


class TestPaths:
    def test_repo_root_exists_and_has_pyproject(self) -> None:
        assert REPO_ROOT.is_dir()
        assert (REPO_ROOT / "pyproject.toml").is_file()

    def test_assets_dir_is_under_repo_root(self) -> None:
        assert AGENTS_ASSETS_DIR.is_relative_to(REPO_ROOT)

    def test_subagents_dir_is_under_assets_dir(self) -> None:
        assert SUBAGENTS_DIR.is_relative_to(AGENTS_ASSETS_DIR)

    def test_duets_dir_is_under_assets_dir(self) -> None:
        assert DUETS_DIR.is_relative_to(AGENTS_ASSETS_DIR)

    def test_templates_dir_is_under_assets_dir(self) -> None:
        assert TEMPLATES_DIR.is_relative_to(AGENTS_ASSETS_DIR)

    def test_manifest_path_is_under_subagents_dir(self) -> None:
        # PR-1 retains the legacy location; PR-4 will move this to manifest/.
        assert MANIFEST_PATH.is_relative_to(SUBAGENTS_DIR)

    def test_manifest_key_path_is_at_repo_root(self) -> None:
        assert MANIFEST_KEY_PATH.parent == REPO_ROOT

    def test_paths_use_pathlib(self) -> None:
        for path in (
            REPO_ROOT,
            AGENTS_ASSETS_DIR,
            SUBAGENTS_DIR,
            DUETS_DIR,
            TEMPLATES_DIR,
            MANIFEST_PATH,
            MANIFEST_KEY_PATH,
        ):
            assert isinstance(path, Path)


# ── prompts ──────────────────────────────────────────────────────────────────


class TestPrompts:
    def test_file_output_instructions_mention_outputs_dir(self) -> None:
        assert "/mnt/session/outputs/" in FILE_OUTPUT_INSTRUCTIONS

    def test_file_output_instructions_is_non_empty_string(self) -> None:
        assert isinstance(FILE_OUTPUT_INSTRUCTIONS, str)
        assert len(FILE_OUTPUT_INSTRUCTIONS) > 0


# ── skills ───────────────────────────────────────────────────────────────────


class TestSkills:
    def test_prebuilt_skill_ids_match_dict_keys(self) -> None:
        for key, info in ANTHROPIC_PREBUILT_SKILLS.items():
            assert info["skill_id"] == key

    def test_format_to_prebuilt_is_consistent(self) -> None:
        # Every prebuilt skill should index every artifact_format it claims
        # to support.
        for skill_id, info in ANTHROPIC_PREBUILT_SKILLS.items():
            formats = info["artifact_formats"]
            assert isinstance(formats, list)
            for fmt in formats:
                assert isinstance(fmt, str)
                assert skill_id in FORMAT_TO_PREBUILT.get(fmt, []), (
                    f"{skill_id} declares support for {fmt} "
                    f"but is missing from FORMAT_TO_PREBUILT[{fmt}]"
                )


# ── artifacts ────────────────────────────────────────────────────────────────


class TestArtifacts:
    def test_format_to_qa_template_covers_every_valid_format(self) -> None:
        for fmt in VALID_ARTIFACT_FORMATS:
            assert fmt in FORMAT_TO_QA_TEMPLATE, f"Missing QA template: {fmt}"

    def test_qa_template_filenames_have_known_suffix(self) -> None:
        for fmt, template in FORMAT_TO_QA_TEMPLATE.items():
            assert template.endswith(".tmpl"), (
                f"Template for {fmt} is not a .tmpl: {template}"
            )

    def test_requires_sonnet_is_subset_of_valid_formats(self) -> None:
        assert REQUIRES_SONNET <= VALID_ARTIFACT_FORMATS
