"""Duet 構成ファイルのロード処理。"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DUETS_DIR = REPO_ROOT / "agents" / "duets"
AGENTS_DIR = REPO_ROOT / "agents" / "agents"
EVIDENCE_DIR = REPO_ROOT / "evidence" / "duets"


def check_api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        print("ERROR: ANTHROPIC_API_KEY が設定されていません")
        print("  export ANTHROPIC_API_KEY='sk-ant-...'")
        sys.exit(1)
    return key


def load_duet(duet_name: str) -> dict:
    """duet.json を読み込む。"""
    duet_path = DUETS_DIR / duet_name / "duet.json"
    if not duet_path.exists():
        print(f"ERROR: デュエットが見つかりません: {duet_path}")
        sys.exit(1)
    with open(duet_path, encoding="utf-8") as f:
        return json.load(f)


def load_agent_config(agent_name: str) -> dict:
    """エージェントの config.json を読み込む。"""
    config_path = AGENTS_DIR / agent_name / "config.json"
    if not config_path.exists():
        print(f"ERROR: エージェント設定が見つかりません: {config_path}")
        sys.exit(1)
    with open(config_path, encoding="utf-8") as f:
        return json.load(f)


def load_skill_md(duet_name: str) -> str | None:
    """デュエットの SKILL.md を読み込む（存在する場合）。"""
    skill_path = DUETS_DIR / duet_name / "skill.md"
    if skill_path.exists():
        return skill_path.read_text(encoding="utf-8")
    skill_path_upper = DUETS_DIR / duet_name / "SKILL.md"
    if skill_path_upper.exists():
        return skill_path_upper.read_text(encoding="utf-8")
    return None
