#!/usr/bin/env python3
"""
Agent Factory — 自然言語からエージェントを自動生成する CLI

ユーザーの自然言語仕様から、以下の4フェーズでエージェントを完全自動生成する:
  Phase 1: Blueprint 生成（agent.md + config.json + test-prompts.json）
  Phase 2: Eval Suite 生成（fixture/ + ground-truth.json + task.json + rubric.md）
  Phase 3: 登録 + バリデーション（マニフェスト + frontmatter + config 検証）
  Phase 4: EDD ループ（eval 実行 → スコア分析 → prompt 改善 → 再 eval）

Usage:
    python scripts/agent-factory.py --spec "請求書から..." [--model haiku]     # 全自動生成
    python scripts/agent-factory.py --spec "..." --skip-edd                    # EDD スキップ
    python scripts/agent-factory.py --improve <agent-name> [--model haiku]     # 既存の改善のみ
    python scripts/agent-factory.py --spec "..." --dry-run                     # API 呼び出しなし

環境変数:
    ANTHROPIC_API_KEY  — Anthropic API キー（必須）
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
AGENTS_DIR = REPO_ROOT / "agents" / "agents"

sys.path.insert(0, str(REPO_ROOT / "scripts"))

MODEL_MAP = {
    "haiku": "claude-haiku-4-5",
    "sonnet": "claude-sonnet-4-6",
    "opus": "claude-opus-4-6",
}


def check_api_key() -> str:
    """ANTHROPIC_API_KEY の存在を確認する。"""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        print("ERROR: ANTHROPIC_API_KEY が設定されていません")
        sys.exit(1)
    return key


def create_client():
    """Anthropic client を作成する。"""
    try:
        import anthropic
    except ImportError:
        print("ERROR: anthropic パッケージが必要です。pip install anthropic を実行してください。")
        sys.exit(1)
    return anthropic.Anthropic()


def phase1_blueprint(client, spec: str, model: str) -> dict:
    """Phase 1: Blueprint 生成 — 自然言語仕様からエージェント定義を生成する。"""
    from agent_factory.blueprint import generate_blueprint, expand_blueprint, save_blueprint

    print("\n" + "=" * 60)
    print("  Phase 1: Blueprint 生成")
    print("=" * 60)
    print(f"  仕様: {spec}")
    print(f"  モデル: {model}")

    resolved_model = MODEL_MAP.get(model, model)
    blueprint = generate_blueprint(client, spec, model=resolved_model)

    print(f"  エージェント名: {blueprint['name']}")
    print(f"  タイプ: {blueprint['agent_type']}")
    print(f"  フォーマット: {blueprint['artifact_format']}")
    print(f"  ツール: {blueprint['tools']}")

    agent_md, config, test_prompts = expand_blueprint(blueprint)
    agent_dir = save_blueprint(blueprint, agent_md, config, test_prompts)

    print(f"  出力先: {agent_dir}")
    print(f"  ファイル: agent.md, config.json, test-prompts.json")

    return blueprint


def phase2_eval_suite(client, blueprint: dict, model: str) -> dict:
    """Phase 2: Eval Suite 生成 — 評価スイートを自動生成する。"""
    from agent_factory.eval_suite import generate_eval_suite

    print("\n" + "=" * 60)
    print("  Phase 2: Eval Suite 生成")
    print("=" * 60)

    resolved_model = MODEL_MAP.get(model, model)
    result = generate_eval_suite(client, blueprint, model=resolved_model)

    print(f"\n  タスク数: {len(result['tasks'])}")
    for task in result["tasks"]:
        marker = " [弱点テスト]" if task in result.get("weakness_tests", []) else ""
        print(f"    - {task}{marker}")

    if result["errors"]:
        print(f"\n  警告: {len(result['errors'])} 件")
        for err in result["errors"]:
            print(f"    - {err}")

    return result


def phase3_validate(agent_name: str) -> list[str]:
    """Phase 3: 登録 + バリデーション — マニフェスト登録 + 全検証を実行する。"""
    print("\n" + "=" * 60)
    print("  Phase 3: 登録 + バリデーション")
    print("=" * 60)

    errors = []

    # 1. マニフェスト登録
    print("  [1/4] マニフェスト登録 ...", end=" ")
    try:
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "manifest.py"), "register", agent_name],
            capture_output=True, text=True, cwd=str(REPO_ROOT),
        )
        if result.returncode != 0:
            errors.append(f"マニフェスト登録失敗: {result.stderr.strip()}")
            print("FAIL")
        else:
            print("OK")
    except Exception as e:
        errors.append(f"マニフェスト登録エラー: {e}")
        print("ERROR")

    # 2. frontmatter バリデーション
    print("  [2/4] frontmatter バリデーション ...", end=" ")
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "validate_subagents.py")],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )
    if result.returncode != 0:
        errors.append(f"frontmatter 検証失敗: {result.stderr.strip()}")
        print("FAIL")
    else:
        print("OK")

    # 3. config.json バリデーション
    print("  [3/4] config.json バリデーション ...", end=" ")
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "validate-config.py"),
         str(AGENTS_DIR / agent_name)],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )
    if result.returncode != 0:
        errors.append(f"config 検証失敗: {result.stderr.strip()}")
        print("FAIL")
    else:
        print("OK")

    # 4. eval ドライラン
    print("  [4/4] eval ドライラン ...", end=" ")
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "eval-agent.py"),
         agent_name, "--dry-run"],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )
    if result.returncode != 0:
        errors.append(f"eval ドライラン失敗: {result.stderr.strip()}")
        print("FAIL")
    else:
        print("OK")

    if errors:
        print(f"\n  バリデーション警告: {len(errors)} 件")
        for err in errors:
            print(f"    - {err}")
    else:
        print("\n  全バリデーション PASS")

    return errors


def phase4_edd(client, agent_name: str, model: str) -> dict:
    """Phase 4: EDD ループ — 評価駆動開発で品質を引き上げる。"""
    from agent_factory.edd_loop import run_edd_loop

    print("\n" + "=" * 60)
    print("  Phase 4: EDD ループ（評価駆動開発）")
    print("=" * 60)

    result = run_edd_loop(client, agent_name, model=model)

    print(f"\n  最終スコア: {result['final_score']}")
    print(f"  目標達成: {'YES' if result['target_reached'] else 'NO'}")
    print(f"  改善回数: {result['improvements_made']}")

    return result


def dry_run_preview(spec: str) -> None:
    """--dry-run モード: Blueprint のプレビューのみ（API 呼び出しなし）。"""
    print("\n" + "=" * 60)
    print("  DRY RUN — API 呼び出しなし")
    print("=" * 60)
    print(f"\n  仕様: {spec}")
    print(f"\n  以下のフェーズが実行されます:")
    print(f"    Phase 1: Blueprint 生成（Messages API × 1）")
    print(f"    Phase 2: Eval Suite 生成（Messages API × 2-5）")
    print(f"    Phase 3: 登録 + バリデーション（ローカル Python）")
    print(f"    Phase 4: EDD ループ（Managed Agents × 1-3 + Messages API × 1-3）")
    print(f"\n  推定コスト（haiku）: ~$0.50-$1.00")
    print(f"  推定時間: 5-15 分")


def main():
    parser = argparse.ArgumentParser(
        description="Agent Factory — 自然言語からエージェントを自動生成",
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--spec",
        type=str,
        help="エージェントの自然言語仕様",
    )
    group.add_argument(
        "--improve",
        type=str,
        metavar="AGENT_NAME",
        help="既存エージェントの EDD ループのみ実行",
    )

    parser.add_argument(
        "--model",
        type=str,
        default="haiku",
        choices=["haiku", "sonnet", "opus"],
        help="使用モデル（デフォルト: haiku）",
    )
    parser.add_argument(
        "--skip-edd",
        action="store_true",
        help="Phase 4（EDD ループ）をスキップ",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="API を呼び出さずにプレビュー",
    )
    parser.add_argument(
        "--target-score",
        type=float,
        default=0.65,
        help="EDD の目標スコア（デフォルト: 0.65）",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=3,
        help="EDD の最大イテレーション数（デフォルト: 3）",
    )

    args = parser.parse_args()

    # --dry-run
    if args.dry_run:
        if args.spec:
            dry_run_preview(args.spec)
        else:
            print("ERROR: --dry-run は --spec と一緒に使用してください")
            sys.exit(1)
        return

    # API キー確認
    check_api_key()
    client = create_client()

    start_time = time.time()

    if args.improve:
        # --improve モード: EDD のみ
        agent_name = args.improve
        agent_dir = AGENTS_DIR / agent_name
        if not agent_dir.exists():
            print(f"ERROR: エージェントが見つかりません: {agent_dir}")
            sys.exit(1)

        result = phase4_edd(client, agent_name, args.model)

    else:
        # --spec モード: 全フェーズ実行
        # Phase 1
        blueprint = phase1_blueprint(client, args.spec, args.model)

        # Phase 2
        eval_result = phase2_eval_suite(client, blueprint, args.model)

        # Phase 3
        validation_errors = phase3_validate(blueprint["name"])

        # Phase 4（オプション）
        if not args.skip_edd:
            edd_result = phase4_edd(client, blueprint["name"], args.model)

    elapsed = time.time() - start_time

    print("\n" + "=" * 60)
    print(f"  完了（{elapsed:.1f} 秒）")
    print("=" * 60)

    if args.spec:
        agent_name = blueprint["name"] if "blueprint" in dir() else "unknown"
        print(f"\n  次のステップ:")
        print(f"    make eval-agent NAME={agent_name} MODEL=haiku TRIALS=3")
        print(f"    make test-agent NAME={agent_name}")


if __name__ == "__main__":
    main()
