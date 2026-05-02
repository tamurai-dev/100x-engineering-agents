"""
duet_runtime — Duet ワークフロー実行エンジンの構成モジュール群。

run-duet.py を論理単位で分割した内部パッケージ。

サブモジュール:
    constants  - モデルマップ、Beta ヘッダ、しきい値などの定数
    loaders    - duet.json / agent config.json のロード
    qa         - QA レスポンスのパース、フィードバック整形、モデルエスカレーション
    sessions   - Managed Agents セッション作成、イベント送受信、ファイル取得
    orchestrator - Multiagent モード用のオーケストレーター構築
"""

from __future__ import annotations

from .constants import (
    BETA_HEADER,
    DEFAULT_ESCALATION_THRESHOLD,
    DEFAULT_MODEL_ESCALATION,
    ESCALATION_IMPROVEMENT_DELTA,
    EVIDENCE_RESPONSE_LIMIT,
    FILE_OUTPUT_INSTRUCTIONS,
    FILES_BETA,
    FORMAT_REQUIRES_SONNET,
    MODEL_MAP,
    MULTIAGENT_BETA,
    ORCHESTRATOR_MAX_QA_PROMPT_CHARS,
    SKILLS_BETA,
)
from .loaders import (
    AGENTS_DIR,
    DUETS_DIR,
    EVIDENCE_DIR,
    REPO_ROOT,
    check_api_key,
    load_agent_config,
    load_duet,
)
from .qa import (
    build_feedback_history,
    parse_qa_result,
    should_escalate_model,
)
from .sessions import (
    create_agent_and_session,
    download_file_content,
    list_session_files,
    list_session_output_files,
    send_and_collect,
)

__all__ = [
    # constants
    "BETA_HEADER",
    "DEFAULT_ESCALATION_THRESHOLD",
    "DEFAULT_MODEL_ESCALATION",
    "ESCALATION_IMPROVEMENT_DELTA",
    "EVIDENCE_RESPONSE_LIMIT",
    "FILE_OUTPUT_INSTRUCTIONS",
    "FILES_BETA",
    "FORMAT_REQUIRES_SONNET",
    "MODEL_MAP",
    "MULTIAGENT_BETA",
    "ORCHESTRATOR_MAX_QA_PROMPT_CHARS",
    "SKILLS_BETA",
    # loaders
    "AGENTS_DIR",
    "DUETS_DIR",
    "EVIDENCE_DIR",
    "REPO_ROOT",
    "check_api_key",
    "load_agent_config",
    "load_duet",
    # qa
    "build_feedback_history",
    "parse_qa_result",
    "should_escalate_model",
    # sessions
    "create_agent_and_session",
    "download_file_content",
    "list_session_files",
    "list_session_output_files",
    "send_and_collect",
]
