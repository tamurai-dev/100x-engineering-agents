#!/usr/bin/env bash
# ============================================================
# pre-commit フックのセットアップスクリプト
#
# Usage:
#   bash scripts/setup-hooks.sh
#
# 前提条件:
#   - Python 3.8+
#   - pip install pre-commit pyyaml jsonschema
# ============================================================

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

echo "=== Subagent バリデーション環境セットアップ ==="

# Python 依存パッケージのインストール
echo "[1/3] Python 依存パッケージをインストール中..."
pip install --quiet pyyaml jsonschema

# pre-commit のインストール（未インストールの場合）
if ! command -v pre-commit &> /dev/null; then
    echo "[2/3] pre-commit をインストール中..."
    pip install --quiet pre-commit
else
    echo "[2/3] pre-commit は既にインストール済み"
fi

# pre-commit hook の登録
echo "[3/3] pre-commit hook を登録中..."
pre-commit install

echo ""
echo "=== セットアップ完了 ==="
echo ""
echo "以下のバリデーションが有効になりました:"
echo "  - agents/agents/*.md のコミット時に frontmatter を自動検証"
echo ""
echo "手動実行:"
echo "  python scripts/validate_subagents.py              # 全件検証"
echo "  python scripts/validate_subagents.py <file.md>    # 個別検証"
echo "  pre-commit run validate-subagent-frontmatter --all-files  # pre-commit 経由"
