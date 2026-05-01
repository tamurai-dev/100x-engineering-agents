#!/usr/bin/env python3
"""Tests for bundle_factory/skill_resolver.py — Skill Resolution Engine."""

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from bundle_factory.skill_resolver import (
    COMMUNITY_SKILLS,
    CUSTOM_SKILLS,
    DEFAULT_PACKAGES,
    FORMAT_TO_COMMUNITY,
    FORMAT_TO_CUSTOM,
    FORMAT_TO_PREBUILT,
    PREBUILT_SKILLS,
    SkillResolution,
    get_community_skill_catalog,
    get_custom_skill_catalog,
    get_full_skill_catalog,
    get_prebuilt_skill_catalog,
    resolve_community_candidates,
    resolve_custom_skills,
    resolve_packages,
    resolve_prebuilt_skills,
    resolve_skills,
)


class TestPrebuiltSkills(unittest.TestCase):
    """Pre-built Anthropic skill matching tests."""

    def test_presentation_matches_pptx(self):
        skills = resolve_prebuilt_skills("presentation")
        self.assertEqual(len(skills), 1)
        self.assertEqual(skills[0]["skill_id"], "pptx")
        self.assertEqual(skills[0]["type"], "anthropic")

    def test_structured_data_matches_xlsx(self):
        skills = resolve_prebuilt_skills("structured_data")
        self.assertEqual(len(skills), 1)
        self.assertEqual(skills[0]["skill_id"], "xlsx")

    def test_document_matches_docx_and_pdf(self):
        skills = resolve_prebuilt_skills("document")
        ids = {s["skill_id"] for s in skills}
        self.assertIn("docx", ids)
        self.assertIn("pdf", ids)

    def test_text_has_no_prebuilt(self):
        skills = resolve_prebuilt_skills("text")
        self.assertEqual(len(skills), 0)

    def test_code_has_no_prebuilt(self):
        skills = resolve_prebuilt_skills("code")
        self.assertEqual(len(skills), 0)

    def test_html_ui_has_no_prebuilt(self):
        skills = resolve_prebuilt_skills("html_ui")
        self.assertEqual(len(skills), 0)

    def test_all_prebuilt_have_version(self):
        for fmt in FORMAT_TO_PREBUILT:
            for s in resolve_prebuilt_skills(fmt):
                self.assertEqual(s["version"], "latest")

    def test_prebuilt_skill_ids(self):
        self.assertEqual(
            set(PREBUILT_SKILLS.keys()), {"pptx", "xlsx", "docx", "pdf"}
        )


class TestCommunityCandidates(unittest.TestCase):
    """Community skill candidate resolution tests."""

    def test_html_ui_has_candidates(self):
        candidates = resolve_community_candidates("html_ui")
        self.assertGreater(len(candidates), 0)
        self.assertIn("frontend-design", candidates)

    def test_code_has_candidates(self):
        candidates = resolve_community_candidates("code")
        self.assertIn("mcp-builder", candidates)

    def test_media_image_has_candidates(self):
        candidates = resolve_community_candidates("media_image")
        self.assertIn("algorithmic-art", candidates)

    def test_keyword_sorting(self):
        candidates = resolve_community_candidates(
            "html_ui", "frontend UI design component"
        )
        # frontend-design should be ranked high due to keyword matches
        self.assertIn("frontend-design", candidates[:3])

    def test_unknown_format_returns_empty(self):
        candidates = resolve_community_candidates("nonexistent")
        self.assertEqual(len(candidates), 0)

    def test_empty_spec_returns_all(self):
        all_candidates = resolve_community_candidates("html_ui", "")
        with_spec = resolve_community_candidates("html_ui", "theme color")
        self.assertEqual(set(all_candidates), set(with_spec))


class TestPackageResolution(unittest.TestCase):
    """Package resolution tests."""

    def test_presentation_packages_when_no_prebuilt(self):
        packages = resolve_packages("presentation")
        self.assertIn("npm", packages)
        self.assertIn("pptxgenjs", packages["npm"])

    def test_presentation_no_packages_when_prebuilt(self):
        packages = resolve_packages("presentation", matched_skill_ids=["pptx"])
        self.assertEqual(packages, {})

    def test_html_ui_packages(self):
        packages = resolve_packages("html_ui")
        self.assertIn("npm", packages)

    def test_text_no_packages(self):
        packages = resolve_packages("text")
        self.assertEqual(packages, {})

    def test_media_video_packages(self):
        packages = resolve_packages("media_video")
        self.assertIn("apt", packages)
        self.assertIn("ffmpeg", packages["apt"])

    def test_structured_data_keeps_pandas_with_xlsx(self):
        """xlsx replaces exceljs/openpyxl/xlsxwriter, but NOT pandas."""
        packages = resolve_packages("structured_data", matched_skill_ids=["xlsx"])
        self.assertIn("pip", packages)
        self.assertIn("pandas", packages["pip"])


class TestResolveSkills(unittest.TestCase):
    """End-to-end skill resolution tests."""

    def test_presentation_full_resolution(self):
        result = resolve_skills("presentation", "pptxでスライド生成")
        self.assertIsInstance(result, SkillResolution)
        self.assertTrue(result.prebuilt_matched)
        self.assertEqual(len(result.skills), 1)
        self.assertEqual(result.skills[0]["skill_id"], "pptx")
        # Pre-built matched -> no packages needed
        self.assertEqual(result.packages, {})

    def test_structured_data_resolution(self):
        result = resolve_skills("structured_data", "Excel分析")
        self.assertTrue(result.prebuilt_matched)
        self.assertEqual(result.skills[0]["skill_id"], "xlsx")
        # xlsx replaces exceljs/openpyxl/xlsxwriter, but NOT pandas
        self.assertEqual(result.packages, {"pip": ["pandas"]})

    def test_html_ui_resolution(self):
        result = resolve_skills("html_ui", "React UIコンポーネント")
        self.assertFalse(result.prebuilt_matched)
        self.assertEqual(len(result.skills), 0)
        self.assertGreater(len(result.community_candidates), 0)
        self.assertIn("npm", result.packages)

    def test_text_resolution(self):
        result = resolve_skills("text", "テキスト要約")
        self.assertFalse(result.prebuilt_matched)
        self.assertEqual(len(result.skills), 0)
        self.assertEqual(result.packages, {})

    def test_code_resolution(self):
        result = resolve_skills("code", "MCPサーバー生成")
        self.assertFalse(result.prebuilt_matched)
        self.assertGreater(len(result.community_candidates), 0)

    def test_summary_contains_prebuilt(self):
        result = resolve_skills("presentation")
        self.assertIn("Pre-built", result.summary)

    def test_summary_contains_community(self):
        result = resolve_skills("html_ui")
        self.assertIn("Community", result.summary)

    def test_document_resolution(self):
        result = resolve_skills("document", "Word文書作成")
        self.assertTrue(result.prebuilt_matched)
        ids = {s["skill_id"] for s in result.skills}
        self.assertTrue(ids & {"docx", "pdf"})


class TestCustomSkills(unittest.TestCase):
    """Custom (self-hosted) skill resolution tests."""

    def test_custom_skills_registry_is_dict(self):
        self.assertIsInstance(CUSTOM_SKILLS, dict)

    def test_format_to_custom_is_dict(self):
        self.assertIsInstance(FORMAT_TO_CUSTOM, dict)

    def test_resolve_custom_skills_empty_registry(self):
        """No custom skills registered → empty result."""
        result = resolve_custom_skills("presentation", "スライド生成")
        self.assertEqual(result, [])

    def test_resolve_skills_includes_custom_field(self):
        """SkillResolution has custom_skills field."""
        result = resolve_skills("presentation")
        self.assertIsInstance(result.custom_skills, list)

    def test_custom_catalog_empty_when_no_skills(self):
        """Custom catalog returns empty string when no skills registered."""
        catalog = get_custom_skill_catalog()
        self.assertEqual(catalog, "")

    def test_custom_skills_structure_when_registered(self):
        """Validate that CUSTOM_SKILLS entries would have required fields."""
        required = {"skill_id", "display_title", "description",
                     "artifact_formats", "keywords"}
        for name, info in CUSTOM_SKILLS.items():
            self.assertTrue(
                required.issubset(info.keys()),
                f"{name}: missing fields {required - info.keys()}"
            )

    def test_format_to_custom_consistency(self):
        for fmt, names in FORMAT_TO_CUSTOM.items():
            for name in names:
                self.assertIn(name, CUSTOM_SKILLS)
                self.assertIn(fmt, CUSTOM_SKILLS[name]["artifact_formats"])


class TestSkillCatalog(unittest.TestCase):
    """Skill catalog generation tests."""

    def test_prebuilt_catalog_contains_all(self):
        catalog = get_prebuilt_skill_catalog()
        for sid in PREBUILT_SKILLS:
            self.assertIn(sid, catalog)

    def test_community_catalog_contains_all(self):
        catalog = get_community_skill_catalog()
        for name in COMMUNITY_SKILLS:
            self.assertIn(name, catalog)

    def test_full_catalog_has_both(self):
        catalog = get_full_skill_catalog()
        self.assertIn("Pre-built", catalog)
        self.assertIn("Community", catalog)

    def test_catalog_not_empty(self):
        self.assertGreater(len(get_full_skill_catalog()), 100)


class TestDataIntegrity(unittest.TestCase):
    """Data structure integrity tests."""

    def test_all_prebuilt_have_required_fields(self):
        required = {"skill_id", "display_title", "description",
                     "artifact_formats", "replaces_packages"}
        for sid, info in PREBUILT_SKILLS.items():
            self.assertEqual(info["skill_id"], sid)
            self.assertTrue(required.issubset(info.keys()), f"{sid}: {info.keys()}")

    def test_all_community_have_required_fields(self):
        required = {"description", "artifact_formats", "keywords"}
        for name, info in COMMUNITY_SKILLS.items():
            self.assertTrue(required.issubset(info.keys()), f"{name}: {info.keys()}")

    def test_format_to_prebuilt_consistency(self):
        for fmt, sids in FORMAT_TO_PREBUILT.items():
            for sid in sids:
                self.assertIn(sid, PREBUILT_SKILLS)
                self.assertIn(fmt, PREBUILT_SKILLS[sid]["artifact_formats"])

    def test_format_to_community_consistency(self):
        for fmt, names in FORMAT_TO_COMMUNITY.items():
            for name in names:
                self.assertIn(name, COMMUNITY_SKILLS)
                self.assertIn(fmt, COMMUNITY_SKILLS[name]["artifact_formats"])


if __name__ == "__main__":
    unittest.main()
