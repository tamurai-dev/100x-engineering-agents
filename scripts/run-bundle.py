#!/usr/bin/env python3
"""
Bundle ワークフロー実行エンジン

Task Agent → QA Agent（fresh-context）→ フィードバック → 再実行 の
ワークフローを Managed Agents API で実行する。

Usage:
    python scripts/run-bundle.py <bundle-name> --input "レビュー対象コード"
    python scripts/run-bundle.py <bundle-name> --input "..." --model haiku
    python scripts/run-bundle.py <bundle-name> --dry-run

環境変数:
    ANTHROPIC_API_KEY  — Anthropic API キー（--dry-run 以外は必須）
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BUNDLES_DIR = REPO_ROOT / "agents" / "bundles"
AGENTS_DIR = REPO_ROOT / "agents" / "agents"
EVIDENCE_DIR = REPO_ROOT / "evidence" / "bundles"

MODEL_MAP = {
    "haiku": "claude-haiku-4-5",
    "sonnet": "claude-sonnet-4-6",
    "opus": "claude-opus-4-6",
}

BETA_HEADER = "managed-agents-2026-04-01"


def check_api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        print("ERROR: ANTHROPIC_API_KEY が設定されていません")
        print("  export ANTHROPIC_API_KEY='sk-ant-...'")
        sys.exit(1)
    return key


def load_bundle(bundle_name: str) -> dict:
    """bundle.json を読み込む。"""
    bundle_path = BUNDLES_DIR / bundle_name / "bundle.json"
    if not bundle_path.exists():
        print(f"ERROR: バンドルが見つかりません: {bundle_path}")
        sys.exit(1)
    with open(bundle_path, encoding="utf-8") as f:
        return json.load(f)


def load_agent_config(agent_name: str) -> dict:
    """エージェントの config.json を読み込む。"""
    config_path = AGENTS_DIR / agent_name / "config.json"
    if not config_path.exists():
        print(f"ERROR: エージェント設定が見つかりません: {config_path}")
        sys.exit(1)
    with open(config_path, encoding="utf-8") as f:
        return json.load(f)


def create_agent_and_session(
    client, config: dict, model_override: str | None, title: str
) -> tuple:
    """Managed Agents API でエージェントとセッションを作成する。"""
    agent_config = dict(config)
    if model_override:
        agent_config["model"] = MODEL_MAP.get(model_override, model_override)

    create_params = {
        "name": agent_config["name"],
        "model": agent_config["model"],
        "system": agent_config.get("system", ""),
    }
    if agent_config.get("description"):
        create_params["description"] = agent_config["description"]
    if agent_config.get("tools"):
        create_params["tools"] = agent_config["tools"]

    agent = client.beta.agents.create(**create_params)
    env = client.beta.environments.create(
        name=f"bundle-{agent_config['name']}-{int(time.time())}",
        config={"type": "cloud", "networking": {"type": "unrestricted"}},
    )
    session = client.beta.sessions.create(
        agent=agent.id,
        environment_id=env.id,
        title=title,
    )
    return agent, env, session


def send_and_collect(client, session_id: str, prompt: str) -> dict:
    """メッセージを送信し、レスポンスを収集する。"""
    messages: list[str] = []
    tool_calls: list[dict] = []
    errors: list[str] = []

    try:
        with client.beta.sessions.events.stream(session_id) as stream:
            client.beta.sessions.events.send(
                session_id,
                events=[
                    {
                        "type": "user.message",
                        "content": [{"type": "text", "text": prompt}],
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
                        tool_calls.append({"name": event.name})
                    case "session.error":
                        err_msg = (
                            str(event.error.message)
                            if hasattr(event, "error")
                            else "unknown error"
                        )
                        errors.append(err_msg)
                    case "session.status_idle":
                        break
                    case "session.status_terminated":
                        errors.append("session terminated")
                        break
    except Exception as e:
        errors.append(f"stream error: {e}")

    # Usage
    session_info = client.beta.sessions.retrieve(session_id)
    usage = {
        "input_tokens": (
            session_info.usage.input_tokens
            if hasattr(session_info, "usage") and session_info.usage
            else 0
        ),
        "output_tokens": (
            session_info.usage.output_tokens
            if hasattr(session_info, "usage") and session_info.usage
            else 0
        ),
    }

    return {
        "response": "\n".join(messages),
        "tool_calls": tool_calls,
        "errors": errors,
        "usage": usage,
    }


def parse_qa_result(response: str) -> dict:
    """QA Agent のレスポンスから JSON 結果をパースする。"""
    # JSON ブロックを抽出
    import re

    json_match = re.search(r"```(?:json)?\s*\n(.*?)\n```", response, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass

    # JSON ブロックなしの場合、全体をパース
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        pass

    # パース失敗
    return {
        "score": 0.0,
        "passed": False,
        "summary": "QA Agent のレスポンスを JSON としてパースできませんでした",
        "feedback": response[:500],
        "parse_error": True,
    }


def run_bundle(
    bundle_name: str,
    user_input: str,
    model: str | None = None,
    dry_run: bool = False,
) -> dict:
    """バンドルワークフローを実行する。"""
    bundle = load_bundle(bundle_name)

    print(f"=== Bundle 実行: {bundle_name} ===")
    print(f"  Task Agent: {bundle['task_agent']['name']}")
    print(f"  QA Agent:   {bundle['qa_agent']['name']}")
    print(f"  Max QA iterations: {bundle['workflow']['qa']['max_iterations']}")
    print(f"  Pass threshold:    {bundle['workflow']['qa']['pass_threshold']}")
    print()

    if dry_run:
        task_config = load_agent_config(bundle["task_agent"]["name"])
        qa_config = load_agent_config(bundle["qa_agent"]["name"])
        print("  [dry-run] Task Agent config: OK")
        print(f"    model: {task_config.get('model')}")
        print(f"    system: {task_config.get('system', '')[:80]}...")
        print()
        print("  [dry-run] QA Agent config: OK")
        print(f"    model: {qa_config.get('model')}")
        print(f"    system: {qa_config.get('system', '')[:80]}...")
        print()
        print("  [dry-run] ワークフロー検証完了。API 呼び出しはスキップしました。")
        return {"dry_run": True, "status": "ok"}

    # API key check
    check_api_key()
    import anthropic

    client = anthropic.Anthropic()

    task_config = load_agent_config(bundle["task_agent"]["name"])
    qa_config = load_agent_config(bundle["qa_agent"]["name"])
    workflow = bundle["workflow"]
    qa_settings = workflow["qa"]

    results = {
        "bundle": bundle_name,
        "input": user_input,
        "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "iterations": [],
        "best_iteration": None,
        "best_score": 0.0,
        "final_status": "incomplete",
    }

    # ── Phase B: Task Agent 実行 ──
    print("[Phase B] Task Agent 実行中...")
    task_agent, task_env, task_session = create_agent_and_session(
        client, task_config, model, f"Bundle Task: {bundle_name}"
    )
    task_result = send_and_collect(client, task_session.id, user_input)

    if task_result["errors"]:
        print(f"  ERROR: Task Agent でエラー発生: {task_result['errors']}")
        results["final_status"] = "task_agent_error"
        results["task_errors"] = task_result["errors"]
        return results

    print(f"  Task Agent 完了 (tokens: {task_result['usage']})")
    task_output = task_result["response"]
    best_output = task_output
    best_score = 0.0

    # ── Phase C: QA Loop ──
    for iteration in range(1, qa_settings["max_iterations"] + 1):
        print(f"\n[Phase C] QA ループ #{iteration}...")

        # QA Agent を fresh-context で起動（新しいセッション）
        qa_agent, qa_env, qa_session = create_agent_and_session(
            client, qa_config, model, f"Bundle QA #{iteration}: {bundle_name}"
        )

        # QA Agent には成果物のみを渡す（タスク実行過程は渡さない = fresh-context）
        qa_prompt = (
            f"以下の成果物を品質検査してください。\n\n"
            f"## 検査対象の成果物\n\n{task_output}\n\n"
            f"## 元の入力（参考）\n\n{user_input}"
        )

        qa_result = send_and_collect(client, qa_session.id, qa_prompt)

        if qa_result["errors"]:
            print(f"  ERROR: QA Agent でエラー発生: {qa_result['errors']}")
            results["iterations"].append({
                "iteration": iteration,
                "qa_errors": qa_result["errors"],
            })
            continue

        # QA 結果をパース
        qa_parsed = parse_qa_result(qa_result["response"])
        score = qa_parsed.get("score", 0.0)
        passed = qa_parsed.get("passed", False)

        iteration_result = {
            "iteration": iteration,
            "score": score,
            "passed": passed,
            "qa_summary": qa_parsed.get("summary", ""),
            "qa_findings_count": len(qa_parsed.get("findings", [])),
            "task_usage": task_result["usage"],
            "qa_usage": qa_result["usage"],
        }
        results["iterations"].append(iteration_result)

        print(f"  QA スコア: {score:.2f} (threshold: {qa_settings['pass_threshold']})")

        # Best score tracking
        if score > best_score:
            best_score = score
            best_output = task_output
            results["best_iteration"] = iteration
            results["best_score"] = score

        if passed or score >= qa_settings["pass_threshold"]:
            print(f"  PASS: QA 合格（スコア {score:.2f}）")
            results["final_status"] = "passed"
            break

        # Convergence check
        if iteration >= 2:
            prev_score = results["iterations"][-2].get("score", 0.0)
            delta = abs(score - prev_score)
            if delta <= qa_settings.get("convergence_delta", 0.02):
                print(f"  収束検出（Δ={delta:.3f} <= {qa_settings['convergence_delta']}）")
                results["final_status"] = "converged"
                break

        # Not passed: give feedback to Task Agent and retry
        if iteration < qa_settings["max_iterations"]:
            feedback = qa_parsed.get("feedback", "品質が不十分です。改善してください。")
            print(f"  FAIL: フィードバックを Task Agent に渡して修正中...")

            # Task Agent に修正依頼（同じセッション）
            retry_prompt = (
                f"QA Agent からのフィードバック:\n\n{feedback}\n\n"
                f"上記のフィードバックに基づいて、前回の出力を改善してください。"
            )
            task_result = send_and_collect(client, task_session.id, retry_prompt)
            if not task_result["errors"]:
                task_output = task_result["response"]
    else:
        results["final_status"] = "max_iterations_reached"

    results["completed_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()

    # ── Phase D: 証跡保存 ──
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d")
    model_label = model or "default"
    evidence_path = EVIDENCE_DIR / f"{timestamp}_{bundle_name}_{model_label}.json"
    with open(evidence_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"\n=== Bundle 実行完了 ===")
    print(f"  最終ステータス: {results['final_status']}")
    print(f"  ベストスコア:   {best_score:.2f} (iteration #{results.get('best_iteration', 'N/A')})")
    print(f"  証跡: {evidence_path}")

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Bundle ワークフロー実行エンジン")
    parser.add_argument("bundle_name", help="バンドル名")
    parser.add_argument("--input", required=False, help="Task Agent への入力")
    parser.add_argument(
        "--model",
        choices=["haiku", "sonnet", "opus"],
        default=None,
        help="モデルのオーバーライド",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="API を呼ばずにワークフロー検証のみ実行",
    )
    args = parser.parse_args()

    if not args.dry_run and not args.input:
        parser.error("--input は必須です（--dry-run 時を除く）")

    run_bundle(
        bundle_name=args.bundle_name,
        user_input=args.input or "",
        model=args.model,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
