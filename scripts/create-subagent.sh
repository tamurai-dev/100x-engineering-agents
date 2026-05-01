#!/usr/bin/env bash
# ============================================================
# 新規 Subagent 作成スクリプト
#
# テンプレートからコピー → 必須フィールド設定 → バリデーション実行
# バリデーションに失敗した場合、ファイルは残るがエラーを明示する。
#
# Usage:
#   bash scripts/create-subagent.sh <agent-name>
#   make create-agent NAME=<agent-name>
#
# エージェント名は小文字+ハイフンのみ（例: my-new-agent）
# ============================================================

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TEMPLATE="$REPO_ROOT/agents/templates/subagent.md.tmpl"
AGENTS_DIR="$REPO_ROOT/agents/agents"
SCHEMA="$REPO_ROOT/agents/schemas/subagent-frontmatter.schema.json"

# ── 引数チェック ──────────────────────────────────
if [ $# -lt 1 ]; then
    echo "ERROR: エージェント名を指定してください"
    echo "  Usage: $0 <agent-name>"
    echo "  例:    $0 my-new-agent"
    exit 1
fi

AGENT_NAME="$1"
TARGET="$AGENTS_DIR/$AGENT_NAME.md"

# ── バリデーション ────────────────────────────────
# 名前フォーマットチェック（小文字+ハイフンのみ）
if ! echo "$AGENT_NAME" | grep -qE '^[a-z0-9][a-z0-9-]*[a-z0-9]$|^[a-z0-9]$'; then
    echo "ERROR: エージェント名は小文字英数字とハイフンのみ使用可能です"
    echo "  OK:  my-agent, code-reviewer, a"
    echo "  NG:  My_Agent, UPPERCASE, -leading-hyphen"
    exit 1
fi

# 重複チェック
if [ -f "$TARGET" ]; then
    echo "ERROR: $TARGET は既に存在します"
    exit 1
fi

# テンプレート存在チェック
if [ ! -f "$TEMPLATE" ]; then
    echo "ERROR: テンプレートが見つかりません: $TEMPLATE"
    exit 1
fi

# ── ファイル作成 ──────────────────────────────────
echo "=== 新規 Subagent 作成: $AGENT_NAME ==="
echo ""

# テンプレートをコピーして name を置換
sed "s/<agent-name>/$AGENT_NAME/g" "$TEMPLATE" > "$TARGET"

echo "[1/4] テンプレートをコピーしました: $TARGET"

# ── マニフェスト登録（HMAC 署名付き）────────────
python3 "$REPO_ROOT/scripts/manifest.py" register "$AGENT_NAME"
echo "[2/4] マニフェストに登録しました（HMAC-SHA256 署名付き）"
echo ""
echo "  次のステップ:"
echo "    1. $TARGET を開いて description, tools 等を編集してください"
echo "    2. frontmatter 以降にシステムプロンプト（本文）を記述してください"
echo "    3. 編集完了後、以下のコマンドでバリデーションを実行してください:"
echo ""
echo "       make validate"
echo "       # または"
echo "       python scripts/validate_subagents.py $TARGET"
echo ""

# ── 即時バリデーション（テンプレート状態） ────────
echo "[3/4] 現在の状態でバリデーションを実行..."
echo ""

# テンプレート状態ではプレースホルダが残っているためFAILが期待される
# ただしエラー内容を表示して、何を修正すべきか明確にする
if python3 "$REPO_ROOT/scripts/validate_subagents.py" "$TARGET" 2>/dev/null; then
    echo ""
    echo "[4/4] バリデーション PASS"
else
    echo ""
    echo "[4/4] バリデーション FAIL — 上記のエラーを修正してください"
    echo "  （テンプレートのプレースホルダが残っている場合は正常な動作です）"
fi

echo ""
echo "=== 作成完了 ==="
echo "  ファイル:       $TARGET"
echo "  マニフェスト:   agents/agents/.manifest.json"
echo "  検証:           make validate"
echo "  レポート:       make report"
