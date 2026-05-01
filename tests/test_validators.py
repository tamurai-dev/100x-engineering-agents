"""Tests for src/duo_agents/validators.py.

Covers the high-level validator functions used by the CLI shims:

* :func:`extract_frontmatter`
* :func:`validate_subagent_frontmatter`
* :func:`validate_agent_config`
* :func:`validate_bundle_dir`
* :func:`load_manifest`

These tests rely on the existing fixtures under ``tests/fixtures/``.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from duo_agents.validators import (  # noqa: E402
    _validate_agent_ref,
    extract_frontmatter,
    load_manifest,
    validate_agent_config,
    validate_bundle_dir,
    validate_subagent_frontmatter,
)

FIXTURES = REPO_ROOT / "tests" / "fixtures"
AGENTS_DIR = REPO_ROOT / "agents" / "agents"
BUNDLES_DIR = REPO_ROOT / "agents" / "bundles"


# ── extract_frontmatter ─────────────────────────────────────────────────────


class TestExtractFrontmatter:
    def test_valid_minimal(self):
        data, err = extract_frontmatter(FIXTURES / "valid-minimal.md")
        assert err is None
        assert data is not None
        assert data["name"] == "valid-minimal"

    def test_no_frontmatter(self):
        data, err = extract_frontmatter(FIXTURES / "invalid-no-frontmatter.md")
        assert data is None
        assert err is not None
        assert "frontmatter" in err.lower() or "frontmatter" in err


# ── validate_subagent_frontmatter ───────────────────────────────────────────


class TestValidateSubagentFrontmatter:
    def test_real_agents_pass(self):
        for agent_md in sorted(AGENTS_DIR.glob("*/agent.md")):
            data, err = extract_frontmatter(agent_md)
            assert err is None, f"{agent_md}: {err}"
            errors = validate_subagent_frontmatter(data, agent_md)
            assert errors == [], f"{agent_md}: {errors}"

    def test_name_mismatch_with_directory(self, tmp_path):
        agent_dir = tmp_path / "code-reviewer"
        agent_dir.mkdir()
        (agent_dir / "agent.md").write_text(
            "---\nname: wrong-name\ndescription: A description goes here.\n---\nbody\n"
        )
        data, _ = extract_frontmatter(agent_dir / "agent.md")
        errors = validate_subagent_frontmatter(data, agent_dir / "agent.md")
        assert any("一致しません" in e for e in errors)

    def test_empty_body(self, tmp_path):
        path = tmp_path / "empty.md"
        path.write_text("---\nname: empty\ndescription: A description goes here.\n---\n")
        data, _ = extract_frontmatter(path)
        errors = validate_subagent_frontmatter(data, path)
        assert any("body" in e for e in errors)


# ── validate_agent_config ───────────────────────────────────────────────────


class TestValidateAgentConfig:
    def test_real_agents_pass(self):
        for agent_dir in sorted(AGENTS_DIR.iterdir()):
            if (agent_dir / "config.json").exists():
                ok, errors = validate_agent_config(agent_dir)
                assert ok, f"{agent_dir.name}: {errors}"

    def test_missing_config(self, tmp_path):
        ok, errors = validate_agent_config(tmp_path)
        assert not ok
        assert any("config.json" in e for e in errors)

    def test_invalid_json(self, tmp_path):
        (tmp_path / "config.json").write_text("not json")
        ok, errors = validate_agent_config(tmp_path)
        assert not ok
        assert any("JSON" in e for e in errors)


# ── validate_bundle_dir ─────────────────────────────────────────────────────


class TestValidateBundleDir:
    def test_real_bundles_pass(self):
        manifest = load_manifest()
        for bundle_dir in sorted(BUNDLES_DIR.iterdir()):
            if not bundle_dir.is_dir():
                continue
            errors = validate_bundle_dir(bundle_dir, manifest)
            assert errors == [], f"{bundle_dir.name}: {errors}"

    def test_missing_bundle_json(self, tmp_path):
        bundle_dir = tmp_path / "fake-bundle"
        bundle_dir.mkdir()
        errors = validate_bundle_dir(bundle_dir, {})
        assert any("bundle.json" in e for e in errors)

    def test_task_qa_must_differ(self):
        manifest = load_manifest()
        bundle_data = {
            "name": "same-agent-bundle",
            "version": "1.0.0",
            "description": "Both Task and QA point to the same agent.",
            "artifact_format": "text",
            "task_agent": {"name": "code-reviewer", "ref": "agents/agents/code-reviewer"},
            "qa_agent": {"name": "code-reviewer", "ref": "agents/agents/code-reviewer"},
            "workflow": {"qa": {"max_iterations": 3, "pass_threshold": 0.80}},
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            bundle_dir = Path(tmpdir) / "same-agent-bundle"
            bundle_dir.mkdir()
            (bundle_dir / "bundle.json").write_text(json.dumps(bundle_data))
            errors = validate_bundle_dir(bundle_dir, manifest)
            assert any("同一です" in e for e in errors)

    def test_bad_qa_logic(self):
        manifest = load_manifest()
        bundle_data = {
            "name": "bad-qa-bundle",
            "version": "1.0.0",
            "description": "convergence_delta is greater than pass_threshold.",
            "artifact_format": "text",
            "task_agent": {"name": "code-reviewer", "ref": "agents/agents/code-reviewer"},
            "qa_agent": {"name": "code-review-qa", "ref": "agents/agents/code-review-qa"},
            "workflow": {
                "qa": {
                    "max_iterations": 3,
                    "pass_threshold": 0.05,
                    "convergence_delta": 0.10,
                }
            },
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            bundle_dir = Path(tmpdir) / "bad-qa-bundle"
            bundle_dir.mkdir()
            (bundle_dir / "bundle.json").write_text(json.dumps(bundle_data))
            errors = validate_bundle_dir(bundle_dir, manifest)
            assert any("convergence_delta" in e for e in errors)


# ── _validate_agent_ref ─────────────────────────────────────────────────────


class TestValidateAgentRef:
    def test_ref_tail_must_match_name(self):
        manifest = load_manifest()
        agent = {"name": "wrong-name", "ref": "agents/agents/code-reviewer"}
        errors = _validate_agent_ref("test-bundle", "Task Agent", agent, manifest)
        assert any("ref 末尾" in e for e in errors)

    def test_unregistered_agent_caught(self):
        manifest = {"version": 1, "agents": {}}
        agent = {"name": "code-reviewer", "ref": "agents/agents/code-reviewer"}
        errors = _validate_agent_ref("test-bundle", "Task Agent", agent, manifest)
        assert any("マニフェストに未登録" in e for e in errors)
