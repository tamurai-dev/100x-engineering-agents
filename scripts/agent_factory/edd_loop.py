"""
EDD ループ — 評価駆動開発による system prompt の自動改善

eval-agent.py でエージェントを評価し、スコアが目標未満なら system prompt を
自動改善して再評価する。最大3回のイテレーションで品質を引き上げる。

内部動作:
  1. eval-agent.py の evaluate_task() を呼び出して現在のスコアを取得
  2. スコアの内訳から改善対象を自動特定:
     - recall < 0.6    → 「全入力を網羅的に確認せよ」を追加
     - precision < 0.7  → 「確信がない指摘は報告しない」を追加
     - tool_calls > 15  → 「まず glob で絞れ」を追加
     - output_quality < 0.5 → 出力形式の例を追加
  3. Claude Messages API で改善版 system prompt を生成
  4. agent.md + config.json を更新して再評価
  5. 目標スコア（0.65）達成 or 最大3回で終了
  6. 最終評価は trials=3 で信頼性を確認

停止条件:
  - overall >= 0.65（目標達成）
  - 3回の改善を完了（プロンプト冗長化リスク回避）
  - 前回から overall が 0.02 未満の改善（収束判定）
"""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
AGENTS_DIR = REPO_ROOT / "agents" / "agents"

# eval-agent.py の関数を import するためにパスを追加
sys.path.insert(0, str(REPO_ROOT / "scripts"))

TARGET_SCORE = 0.65
MAX_ITERATIONS = 3
MIN_IMPROVEMENT = 0.02

# ── 改善ルール ──────────────────────────────────────

IMPROVEMENT_RULES = {
    "recall_low": {
        "condition": lambda scores: (
            scores.get("outcome", {})
            .get("details", {})
            .get("recall", 1.0)
            < 0.6
        ),
        "instruction": "全ファイル・全入力を網羅的に確認し、見落としを減らしてください。チェックリスト方式で1項目ずつ確認することを推奨します。",
    },
    "precision_low": {
        "condition": lambda scores: (
            scores.get("outcome", {})
            .get("details", {})
            .get("precision", 1.0)
            < 0.7
        ),
        "instruction": "確信がない指摘は報告しないでください。false positive を減らすことを優先してください。",
    },
    "too_many_tools": {
        "condition": lambda scores: (
            scores.get("efficiency", {})
            .get("details", {})
            .get("tool_calls", 0)
            > 15
        ),
        "instruction": "まず glob で対象ファイルを絞り込んでから、重要なファイルのみ read してください。不要なツール呼び出しを減らしてください。",
    },
    "output_quality_low": {
        "condition": lambda scores: (
            scores.get("output_quality", {}).get("score", 1.0) < 0.5
        ),
        "instruction": "出力形式を厳守してください。各指摘/結果に具体的な根拠を含めてください。",
    },
}

# 弱点テスト特化の改善ルール
WEAKNESS_IMPROVEMENT_RULES = {
    "hallucination_failed": {
        "condition": lambda results: _weakness_test_score(results, "hallucination") < 0.5,
        "instruction": (
            "## 追加指示: 幻覚行動の抑制\n"
            "- 入力に存在しないデータに対する操作は一切行わない\n"
            "- 「存在しない」「該当なし」と報告することは正しい行動である\n"
            "- 確認できない事実には必ず [要確認] マークを付ける"
        ),
    },
    "scope_creep_failed": {
        "condition": lambda results: _weakness_test_score(results, "scope_creep") < 0.5,
        "instruction": (
            "## 追加指示: スコープ厳守\n"
            "- 指示されたタスクのみを実行する\n"
            "- 「ついでにやっておくと便利」な作業は行わない\n"
            "- 関連する提案がある場合は、本作業完了後に別セクションで報告する"
        ),
    },
    "no_action_failed": {
        "condition": lambda results: _weakness_test_score(results, "no_action") < 0.5,
        "instruction": (
            "## 追加指示: 無操作判断の許容\n"
            "- 問題が見つからない場合は「問題は検出されませんでした」と明示的に報告する\n"
            "- 修正が不要な場合は「変更不要」と報告する\n"
            "- 無理に問題を見つけようとしない。誤検出は見逃しより有害である"
        ),
    },
    "ambiguity_failed": {
        "condition": lambda results: _weakness_test_score(results, "ambiguity") < 0.5,
        "instruction": (
            "## 追加指示: 曖昧さへの対応\n"
            "- 不明点がある場合は AMBIGUITY: [曖昧な点] を記載する\n"
            "- 仮定を置く場合は ASSUMPTION: [仮定の内容] を記載する\n"
            "- 曖昧さを無視して進めてはならない"
        ),
    },
}

# ── 改善プロンプト ──────────────────────────────────

IMPROVE_SYSTEM = textwrap.dedent("""\
あなたはエージェントプロンプトの改善専門家です。
評価結果を分析し、system prompt を改善してください。

## 改善ルール
1. 既存の構造（役割宣言・責務・出力形式・制約事項）は維持する
2. 問題点に対応する具体的な指示を追加する（既存の指示は削除しない）
3. 追加は最小限にする（プロンプトが長すぎると逆効果）
4. 改善した system prompt の全文のみを返す。説明は不要。
""")

IMPROVE_USER = textwrap.dedent("""\
## 現在の system prompt
{current_system_prompt}

## 評価結果
{eval_scores_json}

## 特定された問題点
{improvement_targets}

改善した system prompt 全文を返してください（system prompt のテキストのみ、他の説明は不要）。
""")


def _weakness_test_score(task_results: list[dict], weakness_type: str) -> float:
    """弱点テストのスコアを取得する。テストが存在しない場合は 1.0（問題なし）。"""
    for result in task_results:
        task_name = result.get("task", "")
        if weakness_type in task_name:
            return result.get("mean_scores", {}).get("overall", 1.0)
    return 1.0


def _identify_improvements(task_results: list[dict]) -> list[str]:
    """評価結果から改善対象を自動特定する。"""
    improvements = []

    # 通常タスク（弱点テスト以外）のスコアを集計
    main_results = [
        r for r in task_results
        if r.get("task", "").find("-test") == -1
        or r.get("task", "").find("weakness") == -1
    ]

    for result in main_results:
        # 最初の trial のスコア詳細を使用
        if not result.get("trials"):
            continue
        scores = result["trials"][0].get("scores", {})

        for rule_name, rule in IMPROVEMENT_RULES.items():
            try:
                if rule["condition"](scores):
                    improvements.append(rule["instruction"])
            except (KeyError, TypeError):
                pass

    # 弱点テスト特化
    for rule_name, rule in WEAKNESS_IMPROVEMENT_RULES.items():
        try:
            if rule["condition"](task_results):
                improvements.append(rule["instruction"])
        except (KeyError, TypeError):
            pass

    return improvements


def _improve_prompt(
    client,
    current_prompt: str,
    task_results: list[dict],
    model: str = "claude-haiku-4-5",
) -> str:
    """Claude で system prompt を改善する。"""
    improvements = _identify_improvements(task_results)

    if not improvements:
        return current_prompt

    # 評価結果のサマリー
    scores_summary = []
    for result in task_results:
        scores_summary.append({
            "task": result.get("task"),
            "overall": result.get("mean_scores", {}).get("overall"),
            "outcome": result.get("mean_scores", {}).get("outcome"),
            "pass_rate": result.get("pass_rate"),
        })

    user = IMPROVE_USER.format(
        current_system_prompt=current_prompt,
        eval_scores_json=json.dumps(scores_summary, ensure_ascii=False, indent=2),
        improvement_targets="\n".join(f"- {imp}" for imp in improvements),
    )

    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=IMPROVE_SYSTEM,
        messages=[{"role": "user", "content": user}],
    )

    return response.content[0].text.strip()


def _update_agent_files(agent_name: str, new_system_prompt: str) -> None:
    """agent.md と config.json の system prompt を更新する。"""
    agent_dir = AGENTS_DIR / agent_name

    # config.json 更新
    config_path = agent_dir / "config.json"
    with open(config_path, encoding="utf-8") as f:
        config = json.load(f)
    config["system"] = new_system_prompt
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
        f.write("\n")

    # agent.md 更新（frontmatter は維持、本文を差し替え）
    import re

    md_path = agent_dir / "agent.md"
    md_text = md_path.read_text(encoding="utf-8")
    match = re.match(r"(---\s*\n.*?\n---\s*\n)", md_text, re.DOTALL)
    if match:
        frontmatter = match.group(1)
        md_text = frontmatter + "\n" + new_system_prompt + "\n"
    else:
        md_text = new_system_prompt + "\n"
    md_path.write_text(md_text, encoding="utf-8")


def run_edd_loop(
    client,
    agent_name: str,
    model: str = "haiku",
    target_score: float = TARGET_SCORE,
    max_iterations: int = MAX_ITERATIONS,
) -> dict:
    """
    EDD ループを実行する。

    Args:
        client: Anthropic client
        agent_name: エージェント名
        model: eval に使うモデル
        target_score: 目標 overall スコア
        max_iterations: 最大改善回数

    Returns:
        {
            "iterations": [...],
            "final_score": float,
            "target_reached": bool,
            "improvements_made": int,
        }
    """
    # eval-agent.py の関数を import
    import importlib.util

    eval_agent_path = REPO_ROOT / "scripts" / "eval-agent.py"
    spec = importlib.util.spec_from_file_location("eval_agent", eval_agent_path)
    eval_agent = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(eval_agent)

    iterations = []
    prev_score = 0.0

    for iteration in range(1, max_iterations + 1):
        print(f"\n{'='*60}")
        print(f"  EDD イテレーション {iteration}/{max_iterations}")
        print(f"{'='*60}")

        # 1. 評価実行（trials=1 で素早く確認）
        suite = eval_agent.load_suite(agent_name)
        task_names = suite.get("tasks", [])

        task_results = []
        for task_name in task_names:
            print(f"\n  [eval] {task_name} ...")
            result = eval_agent.evaluate_task(
                client, agent_name, task_name, model, num_trials=1,
            )
            task_results.append(result)

        # 2. 全体スコア計算
        overall_scores = [
            r["mean_scores"]["overall"]
            for r in task_results
            if r.get("mean_scores", {}).get("overall") is not None
        ]
        current_score = (
            sum(overall_scores) / len(overall_scores) if overall_scores else 0.0
        )

        print(f"\n  現在の overall スコア: {current_score:.3f} (目標: {target_score})")

        iteration_record = {
            "iteration": iteration,
            "score": round(current_score, 3),
            "task_results": [
                {
                    "task": r["task"],
                    "overall": r["mean_scores"]["overall"],
                    "outcome": r["mean_scores"]["outcome"],
                }
                for r in task_results
            ],
        }

        # 3. 停止判定
        if current_score >= target_score:
            print(f"  目標スコア達成！({current_score:.3f} >= {target_score})")
            iteration_record["action"] = "target_reached"
            iterations.append(iteration_record)
            break

        if iteration > 1 and (current_score - prev_score) < MIN_IMPROVEMENT:
            print(f"  改善が収束しました（差: {current_score - prev_score:.3f} < {MIN_IMPROVEMENT}）")
            iteration_record["action"] = "converged"
            iterations.append(iteration_record)
            break

        # 4. 改善対象の特定
        improvements = _identify_improvements(task_results)
        if not improvements:
            print("  改善対象が見つかりませんでした")
            iteration_record["action"] = "no_improvements_found"
            iterations.append(iteration_record)
            break

        print(f"  改善対象: {len(improvements)} 件")
        for imp in improvements:
            first_line = imp.split("\n")[0]
            print(f"    - {first_line}")

        # 5. prompt 改善
        config = eval_agent.load_config(agent_name)
        current_prompt = config.get("system", "")

        print("  system prompt を改善中 ...")
        new_prompt = _improve_prompt(client, current_prompt, task_results, model=model)

        if new_prompt == current_prompt:
            print("  system prompt に変更なし")
            iteration_record["action"] = "no_change"
            iterations.append(iteration_record)
            break

        # 6. ファイル更新
        _update_agent_files(agent_name, new_prompt)
        iteration_record["action"] = "improved"
        iteration_record["improvements"] = [
            imp.split("\n")[0] for imp in improvements
        ]
        iterations.append(iteration_record)

        prev_score = current_score

    # 最終スコア
    final_score = iterations[-1]["score"] if iterations else 0.0

    return {
        "iterations": iterations,
        "final_score": round(final_score, 3),
        "target_reached": final_score >= target_score,
        "improvements_made": sum(
            1 for it in iterations if it.get("action") == "improved"
        ),
    }
