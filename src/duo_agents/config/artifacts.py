"""Artifact format registry — single source of truth.

``artifact_format`` is the canonical taxonomy of what a Task Agent produces.
The QA strategy, default model, and skill auto-selection all branch on it.

This module holds the *registry* (the set of valid formats and the simple
mappings). The detailed QA execution pipeline (e.g. ``pptx → pdf → png →
vision``) lives in the QA Strategy Engine, which dereferences these.
"""

from __future__ import annotations

from typing import Final

# All artifact_format values supported by the framework.
# Mirrors ``duet.schema.json`` (which PR-2 will delete in favour of pydantic).
VALID_ARTIFACT_FORMATS: Final[frozenset[str]] = frozenset(
    [
        "text",
        "code",
        "structured_data",
        "document",
        "presentation",
        "html_ui",
        "media_image",
        "media_video",
        "environment_state",
    ]
)

# artifact_format → QA template filename (under TEMPLATES_DIR).
# Formats not listed here fall back to the generic QA template.
FORMAT_TO_QA_TEMPLATE: Final[dict[str, str]] = {
    "presentation": "qa-agent/presentation.md.tmpl",
    "html_ui": "qa-agent/html-ui.md.tmpl",
    "code": "qa-agent/code.md.tmpl",
    # All other formats use generic.
    "text": "qa-agent/generic.md.tmpl",
    "structured_data": "qa-agent/generic.md.tmpl",
    "document": "qa-agent/generic.md.tmpl",
    "media_image": "qa-agent/generic.md.tmpl",
    "media_video": "qa-agent/generic.md.tmpl",
    "environment_state": "qa-agent/generic.md.tmpl",
}

# Formats that require Sonnet or higher by default (visual / structured tasks
# that the cheapest haiku tier cannot handle reliably). The runner uses this
# to decide the *initial* model choice when no explicit model is provided.
REQUIRES_SONNET: Final[frozenset[str]] = frozenset(
    [
        "presentation",
        "structured_data",
        "media_image",
    ]
)
