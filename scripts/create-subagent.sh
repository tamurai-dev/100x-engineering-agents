#!/usr/bin/env bash
# ============================================================
# 新規 Subagent 作成スクリプト
#
# ディレクトリ構造で作成:
#   agents/agents/<name>/
#     ├── agent.md          (Claude Code 用)
#     └── config.json       (Managed Agents API 用)
#
# Usage:
#   bash scripts/create-subagent.sh <agent-name>
#   make create-agent NAME=<agent-name>
#
# エージェント名は小文字+ハイフンのみ（例: my-new-agent）
# ============================================================

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MD_TEMPLATE="$REPO_ROOT/agents/templates/task-agent/agent.md.tmpl"
CONFIG_TEMPLATE="$REPO_ROOT/agents/templates/task-agent/config.json.tmpl"
AGENTS_DIR="$REPO_ROOT/agents/agents"

# ── 引数チェック ──────────────────────────────────
if [ $# -lt 1 ]; then
    echo "ERROR: エージェント名を指定してください"
    echo "  Usage: $0 <agent-name>"
    echo "  例:    $0 my-new-agent"
    exit 1
fi

AGENT_NAME="$1"
TARGET_DIR="$AGENTS_DIR/$AGENT_NAME"
TARGET_MD="$TARGET_DIR/agent.md"
TARGET_CONFIG="$TARGET_DIR/config.json"

# ── バリデーション ────────────────────────────────
# 名前フォーマットチェック（小文字+ハイフンのみ）
if ! echo "$AGENT_NAME" | grep -qE '^[a-z0-9][a-z0-9-]*[a-z0-9]$|^[a-z0-9]$'; then
    echo "ERROR: エージェント名は小文字英数字とハイフンのみ使用可能です"
    echo "  OK:  my-agent, code-reviewer, a"
    echo "  NG:  My_Agent, UPPERCASE, -leading-hyphen"
    exit 1
fi

# 重複チェック
if [ -d "$TARGET_DIR" ]; then
    echo "ERROR: $TARGET_DIR は既に存在します"
    exit 1
fi

# テンプレート存在チェック
for tmpl in "$MD_TEMPLATE" "$CONFIG_TEMPLATE"; do
    if [ ! -f "$tmpl" ]; then
        echo "ERROR: テンプレートが見つかりません: $tmpl"
        exit 1
    fi
done

# ── ディレクトリ & ファイル作成 ───────────────────
echo "=== 新規 Subagent 作成: $AGENT_NAME ==="
echo ""

mkdir -p "$TARGET_DIR"
echo "[1/4] ディレクトリ作成: $TARGET_DIR"

# agent.md
sed "s/<agent-name>/$AGENT_NAME/g" "$MD_TEMPLATE" > "$TARGET_MD"
echo "[2/4] agent.md 作成（Claude Code 用）"

# config.json
sed "s/<agent-name>/$AGENT_NAME/g" "$CONFIG_TEMPLATE" > "$TARGET_CONFIG"
echo "[3/4] config.json 作成（Managed Agents API 用）"

# ── マニフェスト登録（HMAC 署名付き）────────────
python3 "$REPO_ROOT/scripts/manifest.py" register "$AGENT_NAME"
echo "[4/4] マニフェストに登録しました（HMAC-SHA256 署名付き）"

echo ""
echo "  次のステップ:"
echo "    1. $TARGET_MD を編集: description, tools, システムプロンプト"
echo "    2. $TARGET_CONFIG を編集: Managed Agents API パラメータ"
echo "    3. 検証:"
echo ""
echo "       make validate           # agent.md バリデーション"
echo "       make validate-config    # config.json バリデーション + 整合性チェック"
echo ""
echo "=== 作成完了 ==="
echo "  ディレクトリ:   $TARGET_DIR"
echo "  マニフェスト:   agents/agents/.manifest.json"
