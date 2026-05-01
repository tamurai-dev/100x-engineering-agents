"""Anthropic Skills API — built-in skill catalogue.

This module enumerates the prebuilt skills that the Skills API auto-injects
when an agent is created with ``skills=[{type: "anthropic", skill_id: "..."}]``.

Community / custom skills live in the Duet Factory's Skill Resolver because
their selection logic is more involved (LLM-assisted matching, package
resolution, environment setup). This module is intentionally limited to
the small static prebuilt set.
"""

from __future__ import annotations

from typing import Final

# Anthropic prebuilt skills — accessible via type=``anthropic``.
# Keyed by skill_id (the value passed to the Skills API).
ANTHROPIC_PREBUILT_SKILLS: Final[dict[str, dict[str, object]]] = {
    "pptx": {
        "skill_id": "pptx",
        "display_title": "PowerPoint",
        "description": "Create and edit presentations",
        "artifact_formats": ["presentation"],
        "replaces_packages": ["pptxgenjs", "python-pptx"],
    },
    "xlsx": {
        "skill_id": "xlsx",
        "display_title": "Excel",
        "description": "Create and analyze spreadsheets",
        "artifact_formats": ["structured_data"],
        "replaces_packages": ["exceljs", "openpyxl", "xlsxwriter"],
    },
    "docx": {
        "skill_id": "docx",
        "display_title": "Word",
        "description": "Create and edit documents",
        "artifact_formats": ["document"],
        "replaces_packages": ["python-docx", "docx"],
    },
    "pdf": {
        "skill_id": "pdf",
        "display_title": "PDF",
        "description": "Generate PDF documents",
        "artifact_formats": ["document"],
        "replaces_packages": ["reportlab", "fpdf", "pdfkit", "puppeteer"],
    },
}


def _build_format_to_prebuilt() -> dict[str, list[str]]:
    """Reverse-index ``ANTHROPIC_PREBUILT_SKILLS`` by ``artifact_format``."""
    out: dict[str, list[str]] = {}
    for skill_id, info in ANTHROPIC_PREBUILT_SKILLS.items():
        formats = info["artifact_formats"]
        assert isinstance(formats, list)
        for fmt in formats:
            assert isinstance(fmt, str)
            out.setdefault(fmt, []).append(skill_id)
    return out


# Reverse map: artifact_format → list of prebuilt skill_ids that support it.
FORMAT_TO_PREBUILT: Final[dict[str, list[str]]] = _build_format_to_prebuilt()
