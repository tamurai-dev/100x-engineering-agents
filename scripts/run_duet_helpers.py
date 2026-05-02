"""
run-duet.py の純粋関数を再エクスポートするヘルパーモジュール。

run-duet.py はハイフンを含むファイル名のため直接 import できない。
テストスイート (tests/test_run_duet.py) はこのモジュール経由でインポートする。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

# Load run-duet.py as a module despite hyphenated filename
_SCRIPT_PATH = Path(__file__).resolve().parent / "run-duet.py"
_spec = importlib.util.spec_from_file_location("_run_duet", _SCRIPT_PATH)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["_run_duet"] = _mod
_spec.loader.exec_module(_mod)

# Re-export public functions and constants
EVIDENCE_RESPONSE_LIMIT = _mod.EVIDENCE_RESPONSE_LIMIT
MODEL_MAP = _mod.MODEL_MAP
DUETS_DIR = _mod.DUETS_DIR
AGENTS_DIR = _mod.AGENTS_DIR
EVIDENCE_DIR = _mod.EVIDENCE_DIR
DEFAULT_MODEL_ESCALATION = _mod.DEFAULT_MODEL_ESCALATION
DEFAULT_ESCALATION_THRESHOLD = _mod.DEFAULT_ESCALATION_THRESHOLD
ESCALATION_IMPROVEMENT_DELTA = _mod.ESCALATION_IMPROVEMENT_DELTA
FORMAT_REQUIRES_SONNET = _mod.FORMAT_REQUIRES_SONNET
FILE_OUTPUT_INSTRUCTIONS = _mod.FILE_OUTPUT_INSTRUCTIONS

check_api_key = _mod.check_api_key
load_duet = _mod.load_duet
load_agent_config = _mod.load_agent_config
create_agent_and_session = _mod.create_agent_and_session
send_and_collect = _mod.send_and_collect
list_session_files = _mod.list_session_files
list_session_output_files = _mod.list_session_output_files
download_file_content = _mod.download_file_content
parse_qa_result = _mod.parse_qa_result
build_feedback_history = _mod.build_feedback_history
should_escalate_model = _mod.should_escalate_model
run_duet = _mod.run_duet
build_orchestrator_system = _mod.build_orchestrator_system
MULTIAGENT_BETA = _mod.MULTIAGENT_BETA
ORCHESTRATOR_MAX_QA_PROMPT_CHARS = _mod.ORCHESTRATOR_MAX_QA_PROMPT_CHARS
run_duet_multiagent = _mod.run_duet_multiagent
