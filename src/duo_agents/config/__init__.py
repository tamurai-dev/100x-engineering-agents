"""Centralized configuration for Duo Agents.

Importing from ``duo_agents.config`` re-exports the most commonly used
constants. For specific subsets, import from the relevant submodule
(e.g. ``from duo_agents.config.models import MODEL_IDS``).

The goal of this package is to provide a single source of truth for values
that change frequently (model IDs, beta headers) or are reused across many
modules (paths, thresholds, prompts).
"""

from duo_agents.config.artifacts import (
    FORMAT_TO_QA_TEMPLATE,
    REQUIRES_SONNET,
    VALID_ARTIFACT_FORMATS,
)
from duo_agents.config.betas import (
    ALL_BETAS,
    FILES_API_BETA,
    MANAGED_AGENTS_BETA,
    MULTIAGENT_BETA,
    SKILLS_API_BETA,
)
from duo_agents.config.models import (
    DEFAULT_MODEL,
    ESCALATION_ORDER,
    MODEL_IDS,
    ModelCapabilities,
    ModelTier,
)
from duo_agents.config.paths import (
    AGENTS_ASSETS_DIR,
    BUNDLES_DIR,
    EVIDENCE_DIR,
    MANIFEST_KEY_PATH,
    MANIFEST_PATH,
    REPO_ROOT,
    SCHEMAS_DIR,
    SUBAGENTS_DIR,
    TEMPLATES_DIR,
    TESTS_DIR,
)
from duo_agents.config.prompts import FILE_OUTPUT_INSTRUCTIONS
from duo_agents.config.skills import (
    ANTHROPIC_PREBUILT_SKILLS,
    FORMAT_TO_PREBUILT,
)
from duo_agents.config.thresholds import (
    DEFAULT_EDD_CONVERGENCE_DELTA,
    DEFAULT_EDD_MAX_ITERATIONS,
    DEFAULT_EDD_TARGET_OVERALL,
    DEFAULT_ESCALATION_IMPROVEMENT_DELTA,
    DEFAULT_ESCALATION_THRESHOLD,
    DEFAULT_QA_CONVERGENCE_DELTA,
    DEFAULT_QA_MAX_ITERATIONS,
    DEFAULT_QA_PASS_THRESHOLD,
)

__all__ = [
    # artifacts
    "FORMAT_TO_QA_TEMPLATE",
    "REQUIRES_SONNET",
    "VALID_ARTIFACT_FORMATS",
    # betas
    "ALL_BETAS",
    "FILES_API_BETA",
    "MANAGED_AGENTS_BETA",
    "MULTIAGENT_BETA",
    "SKILLS_API_BETA",
    # models
    "DEFAULT_MODEL",
    "ESCALATION_ORDER",
    "MODEL_IDS",
    "ModelCapabilities",
    "ModelTier",
    # paths
    "AGENTS_ASSETS_DIR",
    "BUNDLES_DIR",
    "EVIDENCE_DIR",
    "MANIFEST_KEY_PATH",
    "MANIFEST_PATH",
    "REPO_ROOT",
    "SCHEMAS_DIR",
    "SUBAGENTS_DIR",
    "TEMPLATES_DIR",
    "TESTS_DIR",
    # prompts
    "FILE_OUTPUT_INSTRUCTIONS",
    # skills
    "ANTHROPIC_PREBUILT_SKILLS",
    "FORMAT_TO_PREBUILT",
    # thresholds
    "DEFAULT_EDD_CONVERGENCE_DELTA",
    "DEFAULT_EDD_MAX_ITERATIONS",
    "DEFAULT_EDD_TARGET_OVERALL",
    "DEFAULT_ESCALATION_IMPROVEMENT_DELTA",
    "DEFAULT_ESCALATION_THRESHOLD",
    "DEFAULT_QA_CONVERGENCE_DELTA",
    "DEFAULT_QA_MAX_ITERATIONS",
    "DEFAULT_QA_PASS_THRESHOLD",
]
