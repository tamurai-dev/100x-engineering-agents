#!/usr/bin/env python3
"""
Duet Factory — 自然言語からデュエット（Task Agent + QA Agent）を自動生成する CLI

ユーザーの自然言語仕様から、以下の5フェーズでデュエットを完全自動生成する:
  Phase 1: Duet Blueprint 生成（Task Agent + QA Agent 設計）
  Phase 2: QA Agent テンプレート展開（artifact_format → QA テンプレート自動選択）
  Phase 3: SKILL.md 生成（タスク固有の手順書）
  Phase 4: duet.json + workflow.md 生成
  Phase 5: 登録 + バリデーション（マニフェスト + frontmatter + config 検証）

Usage:
    python scripts/duet-factory.py --spec "pptxgenjsでスライド生成"
    python scripts/duet-factory.py --spec "..." --model haiku
    python scripts/duet-factory.py --spec "..." --format presentation
    python scripts/duet-factory.py --spec "..." --dry-run

環境変数:
    ANTHROPIC_API_KEY  — Anthropic API キー（--dry-run 以外は必須）
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


def phase1_blueprint(client, spec: str, model: str, artifact_format: str | None) -> dict:
    """Phase 1: Duet Blueprint 生成。"""
    from duet_factory.duet_blueprint import generate_duet_blueprint

    print("\n" + "=" * 60)
    print("  Phase 1: Duet Blueprint 生成")
    print("=" * 60)
    print(f"  仕様: {spec}")
    print(f"  モデル: {model}")

    resolved_model = MODEL_MAP.get(model, model)
    blueprint = generate_duet_blueprint(client, spec, model=resolved_model)

    # artifact_format の明示指定があれば上書き
    if artifact_format:
        blueprint["artifact_format"] = artifact_format
        print(f"  artifact_format: {artifact_format}（明示指定）")
    else:
        print(f"  artifact_format: {blueprint['artifact_format']}（LLM 推論）")

    print(f"  デュエット名: {blueprint['duet_name']}")
    print(f"  Task Agent: {blueprint['task_agent_name']}")
    print(f"  タイプ: {blueprint['agent_type']}")
    print(f"  ツール: {blueprint['task_tools']}")

    return blueprint


def phase2_qa_agent(blueprint: dict) -> tuple[str, dict]:
    """Phase 2: QA Agent テンプレート展開。"""
    from duet_factory.duet_blueprint import expand_qa_agent
    from duet_factory.qa_strategy import resolve_qa_strategy

    print("\n" + "=" * 60)
    print("  Phase 2: QA Agent テンプレート展開")
    print("=" * 60)

    strategy = resolve_qa_strategy(blueprint["artifact_format"])
    print(f"  QA テンプレート: {strategy.agent_template}")
    print(f"  QA パイプライン: {strategy.pipeline}")
    print(f"  推奨モデル: {strategy.recommended_model}")

    qa_md, qa_config = expand_qa_agent(blueprint)
    qa_name = blueprint["duet_name"].removesuffix("-duet") + "-qa"
    print(f"  QA Agent 名: {qa_name}")

    return qa_md, qa_config


def phase3_skill(client, blueprint: dict, model: str) -> str:
    """Phase 3: SKILL.md 生成。"""
    from duet_factory.duet_blueprint import generate_skill

    print("\n" + "=" * 60)
    print("  Phase 3: SKILL.md 生成")
    print("=" * 60)

    resolved_model = MODEL_MAP.get(model, model)
    skill_md = generate_skill(client, blueprint, model=resolved_model)

    lines = skill_md.strip().split("\n")
    print(f"  行数: {len(lines)}")
    print(f"  先頭: {lines[0][:60]}...")

    return skill_md


def phase4_duet(blueprint: dict) -> tuple[dict, str]:
    """Phase 4: duet.json + workflow.md 生成。"""
    from duet_factory.duet_blueprint import generate_duet_json, generate_workflow_md

    print("\n" + "=" * 60)
    print("  Phase 4: duet.json + workflow.md 生成")
    print("=" * 60)

    duet_json = generate_duet_json(blueprint)
    workflow_md = generate_workflow_md(blueprint, duet_json)

    print(f"  デュエット: {duet_json['name']}")
    print(f"  artifact_format: {duet_json['artifact_format']}")
    print(f"  QA ループ: 最大 {duet_json['workflow']['qa']['max_iterations']} 回")
    print(f"  合格閾値: {duet_json['workflow']['qa']['pass_threshold']}")

    return duet_json, workflow_md


def phase5_save_and_validate(
    blueprint: dict,
    task_agent_md: str, task_config: dict, task_test_prompts: list,
    qa_agent_md: str, qa_config: dict,
    duet_json: dict, workflow_md: str, skill_md: str,
) -> list[str]:
    """Phase 5: ファイル保存 + 登録 + バリデーション。"""
    from duet_factory.duet_blueprint import save_duet, expand_task_agent

    print("\n" + "=" * 60)
    print("  Phase 5: 保存 + 登録 + バリデーション")
    print("=" * 60)

    # Save files
    paths = save_duet(
        blueprint,
        task_agent_md, task_config, task_test_prompts,
        qa_agent_md, qa_config,
        duet_json, workflow_md, skill_md,
    )

    print(f"  Task Agent: {paths['task_agent_dir']}")
    print(f"  QA Agent:   {paths['qa_agent_dir']}")
    print(f"  Duet:     {paths['duet_dir']}")

    errors: list[str] = []

    # Register Task Agent in manifest
    task_name = blueprint["task_agent_name"]
    qa_name = blueprint["duet_name"].removesuffix("-duet") + "-qa"

    for agent_name in [task_name, qa_name]:
        print(f"  [{agent_name}] マニフェスト登録 ...", end=" ")
        try:
            result = subprocess.run(
                [sys.executable, str(REPO_ROOT / "scripts" / "manifest.py"), "register", agent_name],
                capture_output=True, text=True, cwd=str(REPO_ROOT),
            )
            if result.returncode != 0:
                errors.append(f"マニフェスト登録失敗 ({agent_name}): {result.stderr.strip()}")
                print("FAIL")
            else:
                print("OK")
        except Exception as e:
            errors.append(f"マニフェスト登録エラー ({agent_name}): {e}")
            print("ERROR")

    # Validate
    print("  frontmatter バリデーション ...", end=" ")
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "validate_subagents.py")],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )
    if result.returncode != 0:
        errors.append(f"frontmatter 検証失敗: {result.stderr.strip()}")
        print("FAIL")
    else:
        print("OK")

    print("  config.json バリデーション ...", end=" ")
    for agent_name in [task_name, qa_name]:
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "validate-config.py"),
             str(AGENTS_DIR / agent_name)],
            capture_output=True, text=True, cwd=str(REPO_ROOT),
        )
        if result.returncode != 0:
            errors.append(f"config 検証失敗 ({agent_name}): {result.stderr.strip()}")
    print("OK" if not any("config 検証" in e for e in errors) else "FAIL")

    print("  duet バリデーション ...", end=" ")
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "validate-duet.py")],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )
    if result.returncode != 0:
        errors.append(f"duet 検証失敗: {result.stderr.strip()}")
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


def dry_run_preview(spec: str, artifact_format: str | None) -> None:
    """--dry-run モード。"""
    from duet_factory.qa_strategy import resolve_qa_strategy

    print("\n" + "=" * 60)
    print("  DRY RUN — API 呼び出しなし")
    print("=" * 60)
    print(f"\n  仕様: {spec}")
    if artifact_format:
        strategy = resolve_qa_strategy(artifact_format)
        print(f"  artifact_format: {artifact_format}（明示指定）")
        print(f"  QA テンプレート: {strategy.agent_template}")
        print(f"  QA パイプライン: {strategy.pipeline}")
        print(f"  推奨モデル: {strategy.recommended_model}")
    else:
        print(f"  artifact_format: LLM が推論")
    print(f"\n  以下のフェーズが実行されます:")
    print(f"    Phase 1: Duet Blueprint 生成（Messages API × 1）")
    print(f"    Phase 2: QA Agent テンプレート展開（ローカル）")
    print(f"    Phase 3: SKILL.md 生成（Messages API × 1）")
    print(f"    Phase 4: duet.json + workflow.md 生成（ローカル）")
    print(f"    Phase 5: 登録 + バリデーション（ローカル Python）")
    print(f"\n  推定コスト（haiku）: ~$0.10-$0.30")
    print(f"  推定時間: 1-3 分")


def main():
    parser = argparse.ArgumentParser(
        description="Duet Factory — 自然言語からデュエットを自動生成",
    )
    parser.add_argument(
        "--spec",
        type=str,
        required=True,
        help="デュエットの自然言語仕様",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="haiku",
        choices=["haiku", "sonnet", "opus"],
        help="使用モデル（デフォルト: haiku）",
    )
    parser.add_argument(
        "--format",
        type=str,
        default=None,
        dest="artifact_format",
        choices=[
            "text", "code", "structured_data", "document", "presentation",
            "html_ui", "media_image", "media_video", "environment_state",
        ],
        help="artifact_format を明示指定（省略時は LLM が推論）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="API を呼び出さずにプレビュー",
    )

    args = parser.parse_args()

    if args.dry_run:
        dry_run_preview(args.spec, args.artifact_format)
        return

    # API キー確認
    check_api_key()
    client = create_client()

    start_time = time.time()

    # Phase 1: Blueprint
    blueprint = phase1_blueprint(client, args.spec, args.model, args.artifact_format)

    # Phase 2: QA Agent
    from duet_factory.duet_blueprint import expand_task_agent
    task_agent_md, task_config, task_test_prompts = expand_task_agent(blueprint)
    qa_agent_md, qa_config = phase2_qa_agent(blueprint)

    # Phase 3: SKILL.md
    skill_md = phase3_skill(client, blueprint, args.model)

    # Phase 4: duet.json + workflow.md
    duet_json, workflow_md = phase4_duet(blueprint)

    # Phase 5: Save + Validate
    errors = phase5_save_and_validate(
        blueprint,
        task_agent_md, task_config, task_test_prompts,
        qa_agent_md, qa_config,
        duet_json, workflow_md, skill_md,
    )

    elapsed = time.time() - start_time

    print("\n" + "=" * 60)
    print(f"  完了（{elapsed:.1f} 秒）")
    print("=" * 60)

    duet_name = blueprint["duet_name"]
    task_name = blueprint["task_agent_name"]
    qa_name = duet_name.removesuffix("-duet") + "-qa"

    print(f"\n  生成物:")
    print(f"    Task Agent:  agents/agents/{task_name}/")
    print(f"    QA Agent:    agents/agents/{qa_name}/")
    print(f"    Duet:      agents/duets/{duet_name}/")

    print(f"\n  次のステップ:")
    print(f"    make run-duet-dry NAME={duet_name}")
    print(f"    make run-duet NAME={duet_name} INPUT=\"...\" MODEL=haiku")
    print(f"    make check-all")


if __name__ == "__main__":
    main()
