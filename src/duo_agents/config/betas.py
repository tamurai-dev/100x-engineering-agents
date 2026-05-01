"""Anthropic API Beta header values — single source of truth.

When Anthropic graduates a Beta API to GA, update the relevant constant here.
All call sites in the runner / factory / eval modules dereference these.
"""

from __future__ import annotations

from typing import Final

# Managed Agents API — the core agent execution surface.
MANAGED_AGENTS_BETA: Final[str] = "managed-agents-2026-04-01"

# Files API — used for uploading fixture files / receiving artifact files.
FILES_API_BETA: Final[str] = "files-api-2025-04-14"

# Skills API — Anthropic prebuilt skills (pptx / xlsx / docx / pdf).
SKILLS_API_BETA: Final[str] = "skills-2025-10-02"

# Multiagent Sessions — shared filesystem mode for Actor-Critic execution.
MULTIAGENT_BETA: Final[str] = "multiagent-2026-04-01"

# Convenience: every Beta header currently in use.
ALL_BETAS: Final[list[str]] = [
    MANAGED_AGENTS_BETA,
    FILES_API_BETA,
    SKILLS_API_BETA,
    MULTIAGENT_BETA,
]
