#!/usr/bin/env python3
"""
エージェント品質評価ランナー

Managed Agents API + Files API を使い、fixture 環境でエージェントの品質を多角的に評価する。

Usage:
    python scripts/eval-agent.py <agent-name>                    # 品質評価（haiku, 3 trial）
    python scripts/eval-agent.py <agent-name> --model sonnet     # sonnet で評価
    python scripts/eval-agent.py <agent-name> --trials 5         # 5 trial
    python scripts/eval-agent.py <agent-name> --task python-security  # 特定タスクのみ
    python scripts/eval-agent.py --all                           # 全エージェント評価
    python scripts/eval-agent.py --dry-run                       # 設定確認のみ

環境変数:
    ANTHROPIC_API_KEY  — Anthropic API キー（必須）
"""

from __future__ import annotations

import datetime
import json
import mimetypes
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
AGENTS_DIR = REPO_ROOT / "agents" / "agents"
EVIDENCE_DIR = REPO_ROOT / "evidence" / "evals"

sys.path.insert(0, str(REPO_ROOT / "scripts"))
from graders.code_grader import grade_ground_truth, grade_transcript, grade_output_format
from graders.model_grader import grade_with_rubric
from graders.test_execution_grader import grade_test_execution

MODEL_MAP = {
    "haiku": "claude-haiku-4-5",
    "sonnet": "claude-sonnet-4-6",
    "opus": "claude-opus-4-6",
}

BETA_HEADER = "managed-agents-2026-04-01"

SCORE_WEIGHTS = {
    "outcome": 0.5,
    "efficiency": 0.2,
    "output_quality": 0.3,
}


def check_api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        print("ERROR: ANTHROPIC_API_KEY が設定されていません")
        sys.exit(1)
    return key


def load_config(agent_name: str) -> dict:
    config_path = AGENTS_DIR / agent_name / "config.json"
    if not config_path.exists():
        print(f"ERROR: {config_path} が見つかりません")
        sys.exit(1)
    with open(config_path, encoding="utf-8") as f:
        return json.load(f)


def load_suite(agent_name: str) -> dict:
    suite_path = AGENTS_DIR / agent_name / "evals" / "suite.json"
    if not suite_path.exists():
        print(f"ERROR: {suite_path} が見つかりません")
        sys.exit(1)
    with open(suite_path, encoding="utf-8") as f:
        return json.load(f)


def load_task(agent_name: str, task_name: str) -> dict:
    task_path = AGENTS_DIR / agent_name / "evals" / "tasks" / task_name / "task.json"
    if not task_path.exists():
        print(f"ERROR: {task_path} が見つかりません")
        sys.exit(1)
    with open(task_path, encoding="utf-8") as f:
        return json.load(f)


def list_agents_with_evals() -> list[str]:
    agents = []
    for d in sorted(AGENTS_DIR.iterdir()):
        if d.is_dir() and (d / "evals" / "suite.json").exists():
            agents.append(d.name)
    return agents


def collect_fixture_files(agent_name: str, task_name: str) -> list[Path]:
    """fixture ディレクトリ内の全ファイルを再帰的に収集する。"""
    fixture_dir = AGENTS_DIR / agent_name / "evals" / "tasks" / task_name / "fixture"
    if not fixture_dir.exists():
        return []
    return sorted(f for f in fixture_dir.rglob("*") if f.is_file())


def upload_fixtures(client, fixture_files: list[Path], fixture_base: Path) -> list[dict]:
    """Files API で fixture ファイルをアップロードし、resource マウント情報を返す。"""
    resources = []
    for fpath in fixture_files:
        rel_path = fpath.relative_to(fixture_base)
        mime_type = mimetypes.guess_type(str(fpath))[0] or "text/plain"

        uploaded = client.beta.files.upload(
            file=(fpath.name, fpath.read_bytes(), mime_type)
        )
        resources.append({
            "type": "file",
            "file_id": uploaded.id,
            "mount_path": f"project/{rel_path}",
        })
    return resources


def run_eval_trial(
    client,
    config: dict,
    task: dict,
    resources: list[dict],
    model_override: str | None = None,
    trial_num: int = 1,
) -> dict:
    """1 trial を実行し、全イベントを収集して grading する。"""

    agent_config = dict(config)
    if model_override:
        agent_config["model"] = MODEL_MAP.get(model_override, model_override)

    # エージェント作成
    create_params = {
        "name": agent_config["name"],
        "model": agent_config["model"],
        "system": agent_config.get("system", ""),
    }
    if agent_config.get("description"):
        create_params["description"] = agent_config["description"]
    if agent_config.get("tools"):
        create_params["tools"] = agent_config["tools"]
    if agent_config.get("mcp_servers"):
        create_params["mcp_servers"] = agent_config["mcp_servers"]
    if agent_config.get("skills"):
        create_params["skills"] = agent_config["skills"]

    agent = client.beta.agents.create(**create_params)

    # 環境作成
    env = client.beta.environments.create(
        name=f"eval-{agent_config['name']}-{int(time.time())}",
        config={"type": "cloud", "networking": {"type": "unrestricted"}},
    )

    # セッション作成（fixture をマウント）
    session = client.beta.sessions.create(
        agent={"type": "agent", "id": agent.id, "version": agent.version},
        environment_id=env.id,
        resources=resources if resources else None,
        title=f"Eval: {task['name']} (trial {trial_num})",
    )

    # プロンプト送信 & ストリーミング
    messages = []
    tool_calls_detail = []
    errors = []

    try:
        with client.beta.sessions.events.stream(session.id) as stream:
            client.beta.sessions.events.send(
                session_id=session.id,
                events=[
                    {
                        "type": "user.message",
                        "content": [{"type": "text", "text": task["prompt"]}],
                    },
                ],
            )

            for event in stream:
                match event.type:
                    case "agent.message":
                        for block in event.content:
                            if hasattr(block, "text"):
                                messages.append(block.text)
                    case "agent.tool_use":
                        tool_calls_detail.append({
                            "name": event.name,
                            "type": "agent.tool_use",
                        })
                    case "session.error":
                        errors.append(
                            str(event.error.message)
                            if hasattr(event, "error") and hasattr(event.error, "message")
                            else "unknown error"
                        )
                    case "session.status_idle":
                        if hasattr(event, "stop_reason") and event.stop_reason and event.stop_reason.type == "end_turn":
                            break
                    case "session.status_terminated":
                        errors.append("session terminated")
                        break
    except Exception as e:
        errors.append(f"stream error: {e}")

    # セッション使用量
    session_info = client.beta.sessions.retrieve(session.id)
    usage = {
        "input_tokens": session_info.usage.input_tokens if hasattr(session_info, "usage") and session_info.usage else 0,
        "output_tokens": session_info.usage.output_tokens if hasattr(session_info, "usage") and session_info.usage else 0,
    }

    # 全イベント取得
    all_events = []
    for event in client.beta.sessions.events.list(session.id):
        event_data = {
            "type": event.type,
            "processed_at": str(event.processed_at) if event.processed_at else None,
        }
        match event.type:
            case "agent.message":
                event_data["content"] = [
                    block.text for block in event.content if hasattr(block, "text")
                ]
            case "agent.tool_use" | "agent.custom_tool_use" | "agent.mcp_tool_use":
                event_data["tool_name"] = event.name
                if hasattr(event, "input") and event.input:
                    input_data = event.input
                    if isinstance(input_data, dict):
                        event_data["input"] = {
                            k: (v[:500] if isinstance(v, str) and len(v) > 500 else v)
                            for k, v in input_data.items()
                        }
            case "agent.tool_result":
                if hasattr(event, "content"):
                    raw = str(event.content)
                    if len(raw) > 2000:
                        event_data["content_preview"] = raw[:1000] + "\n...\n" + raw[-1000:]
                    else:
                        event_data["content_preview"] = raw
            case "span.model_request_start":
                pass
            case "span.model_request_end":
                if hasattr(event, "model_usage") and event.model_usage:
                    event_data["model_usage"] = {
                        "input_tokens": event.model_usage.input_tokens,
                        "output_tokens": event.model_usage.output_tokens,
                    }
        all_events.append(event_data)

    full_response = "\n".join(messages)

    # ストリーミングで取得した messages が少ない場合、events から補完する
    # エージェントが bash でファイルに書き出すパターンに対応
    if len(full_response) < 200:
        event_texts = []
        for ev in all_events:
            if ev.get("type") == "agent.message":
                for text in ev.get("content", []):
                    if isinstance(text, str) and text.strip():
                        event_texts.append(text)
            elif ev.get("type") == "agent.tool_result":
                preview = ev.get("content_preview", "")
                if preview:
                    event_texts.append(preview)
        event_response = "\n".join(event_texts)
        if len(event_response) > len(full_response):
            full_response = event_response

    # クリーンアップ
    try:
        _cleanup(client, session.id, env.id, agent.id)
    except Exception:
        pass

    return {
        "trial": trial_num,
        "model": agent_config["model"],
        "agent_id": agent.id,
        "session_id": session.id,
        "environment_id": env.id,
        "response": full_response,
        "response_preview": full_response[:3000],
        "tool_calls": tool_calls_detail,
        "errors": errors,
        "usage": usage,
        "events": all_events,
    }


def _cleanup(client, session_id: str, env_id: str, agent_id: str):
    """リソースをアーカイブする。"""
    for _ in range(10):
        info = client.beta.sessions.retrieve(session_id)
        if info.status != "running":
            break
        time.sleep(2)
    client.beta.sessions.archive(session_id)
    client.beta.environments.archive(env_id)
    client.beta.agents.archive(agent_id)


def _grade_keywords(response: str, keywords: list[str]) -> dict:
    """キーワードベースの outcome 判定。doc-writer / task-planner 用。"""
    response_lower = response.lower()
    matched = [kw for kw in keywords if kw.lower() in response_lower]
    missed = [kw for kw in keywords if kw.lower() not in response_lower]
    score = len(matched) / len(keywords) if keywords else 0.0
    return {
        "score": round(score, 3),
        "matched": matched,
        "missed": missed,
        "total_keywords": len(keywords),
        "matched_count": len(matched),
    }


def grade_trial(
    client,
    trial_result: dict,
    task: dict,
    agent_name: str,
    task_name: str,
) -> dict:
    """1 trial の結果を全 grader で採点する。"""
    scores = {}

    # 1. Outcome Score
    graders_config = task.get("graders", {})

    if "code_based" in graders_config:
        gt_config = graders_config["code_based"]
        grader_type = gt_config.get("type", "ground-truth-match")

        if grader_type == "ground-truth-match":
            gt_path = AGENTS_DIR / agent_name / "evals" / "tasks" / task_name / gt_config.get("ground_truth", "ground-truth.json")
            if gt_path.exists():
                gt_result = grade_ground_truth(trial_result["response"], gt_path)
                scores["outcome"] = {
                    "score": gt_result["f1"],
                    "details": gt_result,
                }
        elif grader_type == "keyword-check":
            keywords = gt_config.get("keywords", [])
            kw_result = _grade_keywords(trial_result["response"], keywords)
            scores["outcome"] = {
                "score": kw_result["score"],
                "details": kw_result,
            }

    if "test_execution" in graders_config:
        exec_result = grade_test_execution(trial_result["events"])
        if "outcome" in scores:
            prev_score = scores["outcome"]["score"]
            scores["outcome"] = {
                "score": round((prev_score + exec_result["score"]) / 2, 3),
                "details": {"code_based": scores["outcome"]["details"], "test_execution": exec_result},
            }
        else:
            scores["outcome"] = {
                "score": exec_result["score"],
                "details": exec_result,
            }

    if "outcome" not in scores:
        scores["outcome"] = {"score": 0.0, "details": {"reason": "no grader configured"}}

    # 2. Efficiency Score
    transcript_result = grade_transcript(trial_result["events"])
    scores["efficiency"] = {
        "score": transcript_result["efficiency_score"],
        "details": transcript_result,
    }

    # 3. Output Quality Score
    output_quality_parts = []

    format_config = graders_config.get("format", {})
    if format_config:
        fmt_result = grade_output_format(trial_result["response"], format_config)
        output_quality_parts.append(("format", fmt_result["format_compliance"]))

    rubric_path = AGENTS_DIR / agent_name / "evals" / "rubric.md"
    task_rubric_path = AGENTS_DIR / agent_name / "evals" / "tasks" / task_name / "rubric.md"
    active_rubric = task_rubric_path if task_rubric_path.exists() else rubric_path

    if active_rubric.exists() and "model_based" in graders_config:
        rubric_result = grade_with_rubric(
            client,
            trial_result["response"],
            active_rubric,
            task_prompt=task.get("prompt", ""),
            model=graders_config["model_based"].get("grader_model", "claude-haiku-4-5"),
        )
        output_quality_parts.append(("rubric", rubric_result["rubric_score"]))
        scores["rubric_detail"] = rubric_result

    if output_quality_parts:
        avg_quality = sum(s for _, s in output_quality_parts) / len(output_quality_parts)
    else:
        avg_quality = 0.5

    scores["output_quality"] = {
        "score": round(avg_quality, 3),
        "details": {name: score for name, score in output_quality_parts},
    }

    # Overall Score
    overall = (
        scores["outcome"]["score"] * SCORE_WEIGHTS["outcome"]
        + scores["efficiency"]["score"] * SCORE_WEIGHTS["efficiency"]
        + scores["output_quality"]["score"] * SCORE_WEIGHTS["output_quality"]
    )
    scores["overall"] = round(overall, 3)

    return scores


def evaluate_task(
    client,
    agent_name: str,
    task_name: str,
    model: str,
    num_trials: int,
) -> dict:
    """1 タスクを num_trials 回実行し、pass@k / pass^k を計算する。"""
    config = load_config(agent_name)
    task = load_task(agent_name, task_name)

    fixture_base = AGENTS_DIR / agent_name / "evals" / "tasks" / task_name / "fixture"
    fixture_files = collect_fixture_files(agent_name, task_name)

    resources = []
    if fixture_files:
        print(f"    fixture アップロード: {len(fixture_files)} ファイル ...", flush=True)
        resources = upload_fixtures(client, fixture_files, fixture_base)

    trials = []
    pass_threshold = task.get("pass_threshold", {}).get("outcome_score", 0.6)

    for trial_num in range(1, num_trials + 1):
        print(f"    Trial {trial_num}/{num_trials} ...", end=" ", flush=True)

        trial_result = run_eval_trial(
            client, config, task, resources,
            model_override=model, trial_num=trial_num,
        )

        scores = grade_trial(client, trial_result, task, agent_name, task_name)
        trial_result["scores"] = scores

        passed = scores["outcome"]["score"] >= pass_threshold
        trial_result["passed"] = passed
        trials.append(trial_result)

        status = "PASS" if passed else "FAIL"
        print(f"{status} (outcome={scores['outcome']['score']:.2f}, "
              f"efficiency={scores['efficiency']['score']:.2f}, "
              f"overall={scores['overall']:.2f})")

    # pass@k / pass^k
    num_passed = sum(1 for t in trials if t["passed"])
    pass_at_k = num_passed > 0
    pass_all_k = num_passed == num_trials

    mean_outcome = sum(t["scores"]["outcome"]["score"] for t in trials) / num_trials
    mean_efficiency = sum(t["scores"]["efficiency"]["score"] for t in trials) / num_trials
    mean_overall = sum(t["scores"]["overall"] for t in trials) / num_trials

    return {
        "task": task_name,
        "model": MODEL_MAP.get(model, model),
        "num_trials": num_trials,
        "pass_at_k": pass_at_k,
        "pass_all_k": pass_all_k,
        "num_passed": num_passed,
        "pass_rate": round(num_passed / num_trials, 3),
        "mean_scores": {
            "outcome": round(mean_outcome, 3),
            "efficiency": round(mean_efficiency, 3),
            "overall": round(mean_overall, 3),
        },
        "trials": [
            {
                "trial": t["trial"],
                "passed": t["passed"],
                "scores": t["scores"],
                "session_id": t["session_id"],
                "usage": t["usage"],
                "response_preview": t["response_preview"],
                "errors": t["errors"],
                "events": t["events"],
            }
            for t in trials
        ],
    }


def save_eval_results(agent_name: str, model: str, task_results: list[dict]) -> Path:
    """評価結果を evidence/evals/ に保存する。"""
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

    date_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    filename = f"{date_str}_{agent_name}_{model}_eval.json"
    filepath = EVIDENCE_DIR / filename

    evidence = {
        "agent": agent_name,
        "model": model,
        "date": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "weights": SCORE_WEIGHTS,
        "tasks": task_results,
        "summary": {
            "total_tasks": len(task_results),
            "all_pass_at_k": all(t["pass_at_k"] for t in task_results),
            "all_pass_all_k": all(t["pass_all_k"] for t in task_results),
            "mean_overall": round(
                sum(t["mean_scores"]["overall"] for t in task_results) / len(task_results), 3
            ) if task_results else 0.0,
        },
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(evidence, f, ensure_ascii=False, indent=2)

    return filepath


def main():
    import argparse

    parser = argparse.ArgumentParser(description="エージェント品質評価ランナー")
    parser.add_argument("agent_name", nargs="?", help="評価対象エージェント名")
    parser.add_argument("--all", action="store_true", help="全エージェントを評価")
    parser.add_argument("--model", default="haiku", help="テストモデル: haiku, sonnet, opus")
    parser.add_argument("--trials", type=int, default=3, help="Trial 数（デフォルト: 3）")
    parser.add_argument("--task", default=None, help="特定タスクのみ評価")
    parser.add_argument("--dry-run", action="store_true", help="API を呼ばずに設定確認")
    args = parser.parse_args()

    if not args.agent_name and not args.all:
        parser.print_help()
        sys.exit(1)

    agents = list_agents_with_evals() if args.all else [args.agent_name]

    if args.dry_run:
        print("=== ドライラン ===")
        for agent_name in agents:
            config = load_config(agent_name)
            suite = load_suite(agent_name)
            tasks = suite.get("tasks", [])
            print(f"\n{agent_name}:")
            print(f"  config.json: OK (model={config['model']})")
            print(f"  suite.json: {len(tasks)} タスク")
            for task_name in tasks:
                task = load_task(agent_name, task_name)
                fixtures = collect_fixture_files(agent_name, task_name)
                print(f"    - {task_name}: {len(fixtures)} fixture ファイル")
                print(f"      graders: {list(task.get('graders', {}).keys())}")
            print(f"  モデル: {args.model} ({MODEL_MAP.get(args.model, args.model)})")
            print(f"  Trial 数: {args.trials}")
        return

    api_key = check_api_key()

    try:
        from anthropic import Anthropic
    except ImportError:
        print("ERROR: anthropic SDK が必要です")
        print("  pip install anthropic")
        sys.exit(1)

    client = Anthropic(api_key=api_key)

    for agent_name in agents:
        suite = load_suite(agent_name)
        task_names = suite.get("tasks", [])

        if args.task:
            if args.task not in task_names:
                print(f"ERROR: タスク '{args.task}' が {agent_name} の suite に存在しません")
                sys.exit(1)
            task_names = [args.task]

        print(f"\n{'='*60}")
        print(f"  {agent_name} / {args.model} ({MODEL_MAP.get(args.model, args.model)})")
        print(f"  {len(task_names)} タスク × {args.trials} trial")
        print(f"{'='*60}")

        task_results = []
        for task_name in task_names:
            print(f"\n  タスク: {task_name}")
            result = evaluate_task(client, agent_name, task_name, args.model, args.trials)
            task_results.append(result)

            status = "PASS" if result["pass_at_k"] else "FAIL"
            reliability = "RELIABLE" if result["pass_all_k"] else "FLAKY"
            print(f"  → {status} ({reliability}): pass@{args.trials}={result['pass_at_k']}, "
                  f"pass^{args.trials}={result['pass_all_k']}, "
                  f"mean_overall={result['mean_scores']['overall']:.3f}")

        filepath = save_eval_results(agent_name, args.model, task_results)
        print(f"\n  証跡: {filepath.relative_to(REPO_ROOT)}")

    print(f"\n{'='*60}")
    print("  評価完了")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
