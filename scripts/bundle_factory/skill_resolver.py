"""
Skill Resolver — artifact_format + SPEC から最適なスキル構成を自動決定する

3段階のスキル解決フロー:
  Step 1: Anthropic pre-built skill match (pptx, xlsx, docx, pdf)
  Step 2: Community skill recommendation (LLM-assisted)
  Step 3: Package + custom skill generation (fallback)

Usage:
    from bundle_factory.skill_resolver import resolve_skills
    result = resolve_skills("presentation", "pptxgenjsでスライド生成")
"""

from __future__ import annotations

import dataclasses


# ── Anthropic pre-built skills (available via type: "anthropic") ──────

PREBUILT_SKILLS: dict[str, dict] = {
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

# Mapping: artifact_format -> list of pre-built skill_ids
FORMAT_TO_PREBUILT: dict[str, list[str]] = {}
for _sid, _info in PREBUILT_SKILLS.items():
    for _fmt in _info["artifact_formats"]:
        FORMAT_TO_PREBUILT.setdefault(_fmt, []).append(_sid)


# ── Community skills (from anthropics/skills repo, uploadable as custom) ──

COMMUNITY_SKILLS: dict[str, dict] = {
    "algorithmic-art": {
        "description": "Generate algorithmic art using code",
        "artifact_formats": ["media_image"],
        "keywords": ["art", "generative", "algorithmic", "creative-coding"],
    },
    "brand-guidelines": {
        "description": "Apply brand guidelines to documents and content",
        "artifact_formats": ["document", "presentation", "html_ui"],
        "keywords": ["brand", "guidelines", "corporate", "identity"],
    },
    "canvas-design": {
        "description": "Create graphic designs using HTML5 Canvas",
        "artifact_formats": ["media_image", "html_ui"],
        "keywords": ["canvas", "design", "graphics", "illustration"],
    },
    "claude-api": {
        "description": "Guide for using Claude API effectively",
        "artifact_formats": ["code"],
        "keywords": ["api", "claude", "anthropic", "integration"],
    },
    "doc-coauthoring": {
        "description": "Collaborative document writing and editing",
        "artifact_formats": ["document", "text"],
        "keywords": ["coauthor", "writing", "editing", "collaboration"],
    },
    "frontend-design": {
        "description": "Design and build frontend UI components",
        "artifact_formats": ["html_ui"],
        "keywords": ["frontend", "ui", "design", "react", "css", "html"],
    },
    "internal-comms": {
        "description": "Create internal communications and memos",
        "artifact_formats": ["text", "document"],
        "keywords": ["memo", "internal", "communication", "corporate"],
    },
    "mcp-builder": {
        "description": "Build MCP (Model Context Protocol) servers",
        "artifact_formats": ["code"],
        "keywords": ["mcp", "server", "protocol", "tool"],
    },
    "skill-creator": {
        "description": "Create new custom skills for Claude",
        "artifact_formats": ["code"],
        "keywords": ["skill", "create", "template", "meta"],
    },
    "slack-gif-creator": {
        "description": "Create animated GIFs for Slack",
        "artifact_formats": ["media_image"],
        "keywords": ["slack", "gif", "animation", "emoji"],
    },
    "theme-factory": {
        "description": "Generate color themes and design systems",
        "artifact_formats": ["html_ui", "structured_data"],
        "keywords": ["theme", "color", "design-system", "palette"],
    },
    "web-artifacts-builder": {
        "description": "Build interactive web artifacts and prototypes",
        "artifact_formats": ["html_ui"],
        "keywords": ["web", "artifact", "prototype", "interactive"],
    },
    "webapp-testing": {
        "description": "Test web applications using automated tools",
        "artifact_formats": ["code"],
        "keywords": ["test", "webapp", "automated", "qa", "playwright"],
    },
}

# Mapping: artifact_format -> list of community skill names
FORMAT_TO_COMMUNITY: dict[str, list[str]] = {}
for _name, _info in COMMUNITY_SKILLS.items():
    for _fmt in _info["artifact_formats"]:
        FORMAT_TO_COMMUNITY.setdefault(_fmt, []).append(_name)


# ── Common packages by artifact_format ──────────────────────────────

DEFAULT_PACKAGES: dict[str, dict[str, list[str]]] = {
    "presentation": {"npm": ["pptxgenjs"]},
    "html_ui": {"npm": ["express"]},
    "media_image": {"apt": ["imagemagick"], "pip": ["pillow"]},
    "media_video": {"apt": ["ffmpeg"]},
    "structured_data": {"pip": ["pandas"]},
}


@dataclasses.dataclass
class SkillResolution:
    """Result of skill resolution."""

    # Skills to attach to the agent (Managed Agents API format)
    skills: list[dict]
    # Packages to pre-install in the environment
    packages: dict[str, list[str]]
    # Whether a pre-built skill was matched
    prebuilt_matched: bool
    # Matched community skill names (for reference/logging)
    community_candidates: list[str]
    # Resolution summary for logging
    summary: str


def resolve_prebuilt_skills(artifact_format: str) -> list[dict]:
    """Step 1: Match artifact_format to Anthropic pre-built skills.

    Returns list of skill dicts in Managed Agents API format.
    """
    skill_ids = FORMAT_TO_PREBUILT.get(artifact_format, [])
    return [
        {"type": "anthropic", "skill_id": sid, "version": "latest"}
        for sid in skill_ids
    ]


def resolve_community_candidates(
    artifact_format: str, spec: str = ""
) -> list[str]:
    """Step 2: Find community skill candidates for the artifact_format.

    Returns list of community skill names, sorted by keyword relevance.
    """
    candidates = FORMAT_TO_COMMUNITY.get(artifact_format, [])
    if not spec:
        return candidates

    spec_lower = spec.lower()
    scored = []
    for name in candidates:
        info = COMMUNITY_SKILLS[name]
        keyword_hits = sum(1 for kw in info["keywords"] if kw in spec_lower)
        name_hit = 1 if name.replace("-", " ") in spec_lower else 0
        scored.append((name, keyword_hits + name_hit))

    scored.sort(key=lambda x: x[1], reverse=True)
    return [name for name, _score in scored]


def resolve_packages(
    artifact_format: str,
    spec: str = "",
    prebuilt_matched: bool = False,
) -> dict[str, list[str]]:
    """Step 3: Determine packages to pre-install.

    If a pre-built skill covers the format, packages for that format
    are not needed (e.g., pptx skill replaces pptxgenjs).
    """
    if prebuilt_matched:
        return {}
    return dict(DEFAULT_PACKAGES.get(artifact_format, {}))


def resolve_skills(
    artifact_format: str,
    spec: str = "",
) -> SkillResolution:
    """Resolve the optimal skill configuration for a bundle.

    Three-step resolution:
      1. Match pre-built Anthropic skills by artifact_format
      2. Find community skill candidates for reference
      3. Determine required packages (only if no pre-built match)

    Args:
        artifact_format: Bundle artifact format (e.g., "presentation")
        spec: Natural language specification for keyword matching

    Returns:
        SkillResolution with skills, packages, and metadata
    """
    # Step 1: Pre-built match
    prebuilt = resolve_prebuilt_skills(artifact_format)
    prebuilt_matched = len(prebuilt) > 0

    # Step 2: Community candidates
    community = resolve_community_candidates(artifact_format, spec)

    # Step 3: Packages (skipped if pre-built matched)
    packages = resolve_packages(artifact_format, spec, prebuilt_matched)

    # Build summary
    parts = []
    if prebuilt:
        ids = [s["skill_id"] for s in prebuilt]
        parts.append(f"Pre-built: {', '.join(ids)}")
    if community:
        parts.append(f"Community candidates: {', '.join(community[:3])}")
    if packages:
        pkg_strs = [
            f"{mgr}: {', '.join(pkgs)}" for mgr, pkgs in packages.items()
        ]
        parts.append(f"Packages: {'; '.join(pkg_strs)}")
    if not parts:
        parts.append("No specific skills or packages resolved")

    summary = " | ".join(parts)

    return SkillResolution(
        skills=prebuilt,
        packages=packages,
        prebuilt_matched=prebuilt_matched,
        community_candidates=community,
        summary=summary,
    )


def get_prebuilt_skill_catalog() -> str:
    """Return a formatted catalog of pre-built skills for LLM prompts."""
    lines = ["## Anthropic Pre-built Skills\n"]
    for sid, info in PREBUILT_SKILLS.items():
        lines.append(
            f"- **{sid}** ({info['display_title']}): {info['description']}"
        )
        lines.append(
            f"  Artifact formats: {', '.join(info['artifact_formats'])}"
        )
        lines.append(
            f"  Replaces packages: {', '.join(info['replaces_packages'])}"
        )
        lines.append("")
    return "\n".join(lines)


def get_community_skill_catalog() -> str:
    """Return a formatted catalog of community skills for LLM prompts."""
    lines = ["## Community Skills (uploadable as custom skills)\n"]
    for name, info in COMMUNITY_SKILLS.items():
        lines.append(f"- **{name}**: {info['description']}")
        lines.append(
            f"  Artifact formats: {', '.join(info['artifact_formats'])}"
        )
        lines.append(f"  Keywords: {', '.join(info['keywords'])}")
        lines.append("")
    return "\n".join(lines)


def get_full_skill_catalog() -> str:
    """Return a combined catalog of all available skills for LLM prompts."""
    return get_prebuilt_skill_catalog() + "\n" + get_community_skill_catalog()
