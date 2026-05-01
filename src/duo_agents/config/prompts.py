"""Common prompt fragments shared between Task / QA / Orchestrator agents.

Centralizing these strings means a wording fix only needs to land once.
"""

from __future__ import annotations

from typing import Final

# Appended to the Task Agent prompt to ensure artifact files actually land
# in ``/mnt/session/outputs/`` instead of the agent merely *describing* what
# it would produce.
FILE_OUTPUT_INSTRUCTIONS: Final[str] = (
    "\n\n---\n"
    "## IMPORTANT: File Output Rules\n\n"
    "1. Save ALL generated artifacts to `/mnt/session/outputs/`.\n"
    "2. After saving, run `ls -la /mnt/session/outputs/` to verify "
    "the files exist and are non-empty.\n"
    "3. If a file is missing or empty, regenerate and save it again.\n"
    "4. Do NOT just describe what you would create — actually create "
    "the files and save them to the output directory.\n"
)
