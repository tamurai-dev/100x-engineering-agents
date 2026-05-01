"""
run-bundle.py の純粋関数を再エクスポートするヘルパーモジュール。

run-bundle.py はハイフンを含むファイル名のため直接 import できない。
テストスイート (tests/test_run_bundle.py) はこのモジュール経由でインポートする。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

# Load run-bundle.py as a module despite hyphenated filename
_SCRIPT_PATH = Path(__file__).resolve().parent / "run-bundle.py"
_spec = importlib.util.spec_from_file_location("_run_bundle", _SCRIPT_PATH)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["_run_bundle"] = _mod
_spec.loader.exec_module(_mod)

# Re-export public functions and constants
EVIDENCE_RESPONSE_LIMIT = _mod.EVIDENCE_RESPONSE_LIMIT
MODEL_MAP = _mod.MODEL_MAP
BUNDLES_DIR = _mod.BUNDLES_DIR
AGENTS_DIR = _mod.AGENTS_DIR
EVIDENCE_DIR = _mod.EVIDENCE_DIR
DEFAULT_MODEL_ESCALATION = _mod.DEFAULT_MODEL_ESCALATION
DEFAULT_ESCALATION_THRESHOLD = _mod.DEFAULT_ESCALATION_THRESHOLD
ESCALATION_IMPROVEMENT_DELTA = _mod.ESCALATION_IMPROVEMENT_DELTA

check_api_key = _mod.check_api_key
load_bundle = _mod.load_bundle
load_agent_config = _mod.load_agent_config
load_skill_md = _mod.load_skill_md
create_agent_and_session = _mod.create_agent_and_session
send_and_collect = _mod.send_and_collect
list_session_files = _mod.list_session_files
list_session_output_files = _mod.list_session_output_files
download_file_content = _mod.download_file_content
parse_qa_result = _mod.parse_qa_result
build_skill_preamble = _mod.build_skill_preamble
build_feedback_history = _mod.build_feedback_history
should_escalate_model = _mod.should_escalate_model
run_bundle = _mod.run_bundle
build_orchestrator_system = _mod.build_orchestrator_system
MULTIAGENT_BETA = _mod.MULTIAGENT_BETA
ORCHESTRATOR_MAX_QA_PROMPT_CHARS = _mod.ORCHESTRATOR_MAX_QA_PROMPT_CHARS
run_bundle_multiagent = _mod.run_bundle_multiagent
