#!/usr/bin/env bash
# ============================================================
# 初期セットアップスクリプト
#
# 以下を自動で行う:
#   1. Python 依存パッケージの確認
#   2. HMAC 署名鍵の生成（未存在時）
#   3. マニフェスト HMAC の初期化（クローン直後用）
#   4. pre-commit hook の登録
#
# Usage:
#   bash scripts/setup-hooks.sh
#   make setup
#
# 前提条件:
#   - Python 3.10+
#   - pip install -e ".[dev]" 済み（または pyyaml, jsonschema がインストール済み）
# ============================================================

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

echo "=== 100x Engineering Agents セットアップ ==="
echo ""

# ── Step 1: Python 依存パッケージの確認 ──────────
echo "[1/4] Python 依存パッケージを確認中..."
MISSING=""
python3 -c "import yaml" 2>/dev/null || MISSING="pyyaml"
python3 -c "import jsonschema" 2>/dev/null || MISSING="$MISSING jsonschema"

if [ -n "$MISSING" ]; then
    echo "  依存パッケージが不足しています: $MISSING"
    echo "  以下のコマンドでインストールしてください:"
    echo ""
    echo "    pip install -e \".[dev]\""
    echo ""
    echo "  または最小構成:"
    echo ""
    echo "    pip install pyyaml jsonschema"
    echo ""
    exit 1
fi
echo "  OK: pyyaml, jsonschema を検出"

# ── Step 2: HMAC 署名鍵の生成 ─────────────────
echo "[2/4] HMAC 署名鍵を確認中..."
KEY_FILE="$REPO_ROOT/.manifest-key"
if [ -f "$KEY_FILE" ]; then
    echo "  OK: .manifest-key は既に存在します"
else
    python3 -c "
import os
key = os.urandom(32).hex()
with open('.manifest-key', 'w') as f:
    f.write(key)
print('  生成しました: .manifest-key')
print('  注意: この鍵はリポジトリにコミットしないでください（.gitignore に含まれています）')
"
fi

# ── Step 3: マニフェスト HMAC の再署名 ─────────
echo "[3/4] マニフェスト HMAC を確認中..."
VERIFY_RESULT=$(python3 "$REPO_ROOT/scripts/manifest.py" verify 2>&1) || true
if echo "$VERIFY_RESULT" | grep -q "FAIL"; then
    echo "  HMAC 不一致を検出。ローカル鍵で再署名します..."
    python3 -c "
import json, sys
sys.path.insert(0, 'scripts')
from manifest import get_or_create_key, compute_hmac, MANIFEST_PATH

if not MANIFEST_PATH.exists():
    print('  マニフェストが見つかりません。make manifest-init を実行してください。')
    sys.exit(0)

key = get_or_create_key()
manifest = json.loads(MANIFEST_PATH.read_text())
count = 0
for name, entry in manifest['agents'].items():
    new_hmac = compute_hmac(key, name, entry['file'], entry['created_at'])
    if entry['hmac_sha256'] != new_hmac:
        entry['hmac_sha256'] = new_hmac
        count += 1

if count > 0:
    with open(MANIFEST_PATH, 'w') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2, sort_keys=False)
        f.write('\n')
    print(f'  {count} 件のエントリを再署名しました')
else:
    print('  OK: 全エントリの署名が一致しています')
"
else
    echo "  OK: 全エントリの署名が一致しています"
fi

# ── Step 4: pre-commit hook の登録 ─────────────
echo "[4/4] pre-commit hook を確認中..."
if ! command -v pre-commit &> /dev/null; then
    echo "  pre-commit が見つかりません。インストールします..."
    pip install --quiet pre-commit
fi
pre-commit install
echo "  OK: pre-commit hook を登録しました"

echo ""
echo "=== セットアップ完了 ==="
echo ""
echo "次のステップ:"
echo "  1. API キーをセット:  export ANTHROPIC_API_KEY=\"sk-ant-...\""
echo "  2. エージェントを作る: make create-smart-agent SPEC=\"...\""
echo "  3. 全コマンド一覧:    make help"
