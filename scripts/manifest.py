#!/usr/bin/env python3
"""
Subagent マニフェスト管理ツール

agents/agents/.manifest.json の管理・検証を行う。
HMAC-SHA256 署名により、create-subagent.sh を経由せずに作成された
エージェントファイルを検出する。

Usage:
    python scripts/manifest.py register <agent-name>   # マニフェストに登録（HMAC署名付き）
    python scripts/manifest.py verify                   # 全エントリの署名検証
    python scripts/manifest.py verify-staged            # git staged の新規ファイルを検証
    python scripts/manifest.py init                     # 既存エージェントを一括登録
    python scripts/manifest.py show                     # マニフェスト内容を表示
"""

from __future__ import annotations

import datetime
import hashlib
import hmac
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = REPO_ROOT / "agents" / "agents" / ".manifest.json"
KEY_PATH = REPO_ROOT / ".manifest-key"
AGENTS_DIR = REPO_ROOT / "agents" / "agents"

# ── 鍵管理 ─────────────────────────────────────────

def get_or_create_key() -> bytes:
    """HMAC 鍵を取得する。なければ生成する。"""
    import os

    # 1. 環境変数から取得
    env_key = os.environ.get("MANIFEST_HMAC_KEY")
    if env_key:
        return env_key.encode("utf-8")

    # 2. ファイルから取得（なければ生成）
    if KEY_PATH.exists():
        return KEY_PATH.read_bytes().strip()

    # 3. 新規生成
    key = os.urandom(32).hex().encode("utf-8")
    KEY_PATH.write_bytes(key)
    print(f"HMAC 鍵を生成しました: {KEY_PATH}")
    print(f"  この鍵はリポジトリにコミットしないでください（.gitignore に含まれています）")
    return key


def compute_hmac(key: bytes, agent_name: str, filepath: str, created_at: str) -> str:
    """HMAC-SHA256 署名を計算する。"""
    message = f"{agent_name}:{filepath}:{created_at}".encode("utf-8")
    return hmac.new(key, message, hashlib.sha256).hexdigest()


# ── マニフェスト操作 ────────────────────────────────

def load_manifest() -> dict:
    """マニフェストを読み込む。なければ初期構造を返す。"""
    if MANIFEST_PATH.exists():
        with open(MANIFEST_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {"version": 1, "agents": {}}


def save_manifest(manifest: dict) -> None:
    """マニフェストを保存する。"""
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2, sort_keys=False)
        f.write("\n")


def register_agent(agent_name: str) -> bool:
    """エージェントをマニフェストに登録する（HMAC 署名付き）。"""
    key = get_or_create_key()
    manifest = load_manifest()

    filepath = f"agents/agents/{agent_name}.md"
    created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    signature = compute_hmac(key, agent_name, filepath, created_at)

    manifest["agents"][agent_name] = {
        "file": filepath,
        "created_at": created_at,
        "created_by": "create-subagent.sh",
        "hmac_sha256": signature,
    }

    save_manifest(manifest)
    return True


def verify_all() -> tuple[int, int, list[str]]:
    """全エントリの HMAC 署名を検証する。"""
    key = get_or_create_key()
    manifest = load_manifest()

    passed = 0
    failed = 0
    errors = []

    for agent_name, entry in manifest["agents"].items():
        filepath = entry.get("file", "")
        created_at = entry.get("created_at", "")
        stored_hmac = entry.get("hmac_sha256", "")

        expected_hmac = compute_hmac(key, agent_name, filepath, created_at)

        if hmac.compare_digest(stored_hmac, expected_hmac):
            passed += 1
        else:
            failed += 1
            errors.append(f"  FAIL: {agent_name} — HMAC 署名が不正です")

        # ファイル存在チェック
        full_path = REPO_ROOT / filepath
        if not full_path.exists():
            errors.append(f"  WARN: {agent_name} — ファイルが存在しません: {filepath}")

    # agents/ に存在するがマニフェストに登録されていないファイル
    for md_file in sorted(AGENTS_DIR.glob("*.md")):
        name = md_file.stem
        if name not in manifest["agents"]:
            failed += 1
            errors.append(f"  FAIL: {name} — マニフェスト未登録（make create-agent NAME={name} を実行してください）")

    return passed, failed, errors


def verify_staged() -> tuple[int, int, list[str]]:
    """git staged の新規 agents/agents/*.md ファイルを検証する。"""
    key = get_or_create_key()
    manifest = load_manifest()

    # git diff --staged で新規追加ファイルを取得
    try:
        result = subprocess.run(
            ["git", "diff", "--staged", "--name-only", "--diff-filter=A"],
            capture_output=True, text=True, cwd=str(REPO_ROOT)
        )
        new_files = [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
    except Exception:
        new_files = []

    # agents/agents/*.md のみフィルタ
    new_agents = [f for f in new_files if f.startswith("agents/agents/") and f.endswith(".md")]

    if not new_agents:
        return 0, 0, []  # 新規エージェントファイルなし

    passed = 0
    failed = 0
    errors = []

    for filepath in new_agents:
        agent_name = Path(filepath).stem

        if agent_name not in manifest["agents"]:
            failed += 1
            errors.append(
                f"  REJECT: {filepath}\n"
                f"          マニフェスト未登録です。以下のコマンドで作成してください:\n"
                f"          make create-agent NAME={agent_name}"
            )
            continue

        entry = manifest["agents"][agent_name]
        created_at = entry.get("created_at", "")
        stored_hmac = entry.get("hmac_sha256", "")
        expected_hmac = compute_hmac(key, agent_name, entry.get("file", filepath), created_at)

        if hmac.compare_digest(stored_hmac, expected_hmac):
            passed += 1
        else:
            failed += 1
            errors.append(
                f"  REJECT: {filepath}\n"
                f"          HMAC 署名が不正です。マニフェストが手動で改竄された可能性があります。\n"
                f"          正規の手順: make create-agent NAME={agent_name}"
            )

    return passed, failed, errors


def init_existing() -> None:
    """既存エージェントを一括でマニフェストに登録する。"""
    key = get_or_create_key()
    manifest = load_manifest()

    count = 0
    for md_file in sorted(AGENTS_DIR.glob("*.md")):
        agent_name = md_file.stem
        if agent_name in manifest["agents"]:
            print(f"  SKIP: {agent_name}（登録済み）")
            continue

        filepath = f"agents/agents/{agent_name}.md"
        created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        signature = compute_hmac(key, agent_name, filepath, created_at)

        manifest["agents"][agent_name] = {
            "file": filepath,
            "created_at": created_at,
            "created_by": "initial-seed",
            "hmac_sha256": signature,
        }
        count += 1
        print(f"  REGISTER: {agent_name}")

    save_manifest(manifest)
    print(f"\n{count} エージェントを登録しました → {MANIFEST_PATH.relative_to(REPO_ROOT)}")


def show() -> None:
    """マニフェスト内容を表示する。"""
    manifest = load_manifest()
    agents = manifest.get("agents", {})
    print(f"マニフェスト: {MANIFEST_PATH.relative_to(REPO_ROOT)}")
    print(f"登録数: {len(agents)}")
    print()
    for name, entry in agents.items():
        sig = entry.get("hmac_sha256", "N/A")[:16] + "..."
        by = entry.get("created_by", "unknown")
        at = entry.get("created_at", "unknown")
        print(f"  {name}")
        print(f"    created_by: {by}")
        print(f"    created_at: {at}")
        print(f"    hmac:       {sig}")


# ── メイン ──────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]

    if command == "register" and len(sys.argv) >= 3:
        agent_name = sys.argv[2]
        if register_agent(agent_name):
            print(f"OK: {agent_name} をマニフェストに登録しました")
        sys.exit(0)

    elif command == "verify":
        passed, failed, errors = verify_all()
        print(f"マニフェスト検証: {passed} passed / {failed} failed")
        for e in errors:
            print(e)
        sys.exit(1 if failed > 0 else 0)

    elif command == "verify-staged":
        passed, failed, errors = verify_staged()
        if passed == 0 and failed == 0:
            sys.exit(0)  # 新規ファイルなし
        print(f"Staged ファイル検証: {passed} passed / {failed} failed")
        for e in errors:
            print(e)
        sys.exit(1 if failed > 0 else 0)

    elif command == "init":
        init_existing()
        sys.exit(0)

    elif command == "show":
        show()
        sys.exit(0)

    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
