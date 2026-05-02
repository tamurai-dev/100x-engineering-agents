"""Duet ランタイムの定数群。"""

from __future__ import annotations

MODEL_MAP = {
    "haiku": "claude-haiku-4-5",
    "sonnet": "claude-sonnet-4-6",
    "opus": "claude-opus-4-6",
}

BETA_HEADER = "managed-agents-2026-04-01"
FILES_BETA = "files-api-2025-04-14"
SKILLS_BETA = "skills-2025-10-02"
MULTIAGENT_BETA = "multiagent-2026-04-01"

# Default model escalation order and threshold
DEFAULT_MODEL_ESCALATION = ["haiku", "sonnet"]
DEFAULT_ESCALATION_THRESHOLD = 0.40
ESCALATION_IMPROVEMENT_DELTA = 0.05

# Max chars of task_response to store in evidence
EVIDENCE_RESPONSE_LIMIT = 2000

# QA loop iteration limit for orchestrator prompt
ORCHESTRATOR_MAX_QA_PROMPT_CHARS = 4000

# artifact_format values that require higher-tier models by default
FORMAT_REQUIRES_SONNET = {"presentation", "structured_data", "media_image"}

# File output instructions appended to Task Agent prompt
FILE_OUTPUT_INSTRUCTIONS = (
    "\n\n---\n"
    "## IMPORTANT: File Output Rules\n\n"
    "1. Save ALL generated artifacts to `/mnt/session/outputs/`.\n"
    "2. After saving, run `ls -la /mnt/session/outputs/` to verify "
    "the files exist and are non-empty.\n"
    "3. If a file is missing or empty, regenerate and save it again.\n"
    "4. Do NOT just describe what you would create — actually create "
    "the files and save them to the output directory.\n"
)
