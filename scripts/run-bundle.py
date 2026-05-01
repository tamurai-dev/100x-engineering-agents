#!/usr/bin/env python3
"""
Bundle ワークフロー実行エンジン v2

Task Agent → QA Agent（fresh-context）→ フィードバック → 再実行 の
ワークフローを Managed Agents API で実行する。

v2 改善点:
  - SKILL.md 注入（pre_task.read_skills）
  - Files API 連携（セッション出力ファイルの QA Agent 受け渡し）
  - フィードバック蓄積（全ラウンドの指摘を Task Agent に渡す）
  - 証跡詳細化（task_response 抜粋、tool_calls、出力ファイル一覧）
  - --verbose フラグ（デバッグ用詳細ログ）
  - Anthropic Skills API 連携（プリビルト pptx/xlsx/docx/pdf + カスタムスキル）
  - Environment packages 対応（apt/npm/pip 等のプリインストール）

Usage:
    python scripts/run-bundle.py <bundle-name> --input "レビュー対象コード"
    python scripts/run-bundle.py <bundle-name> --input "..." --model haiku
    python scripts/run-bundle.py <bundle-name> --input "..." --verbose
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
FILES_BETA = "files-api-2025-04-14"
SKILLS_BETA = "skills-2025-10-02"

# Max chars of task_response to store in evidence
EVIDENCE_RESPONSE_LIMIT = 2000


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


def load_skill_md(bundle_name: str) -> str | None:
    """バンドルの SKILL.md を読み込む（存在する場合）。"""
    skill_path = BUNDLES_DIR / bundle_name / "skill.md"
    if skill_path.exists():
        return skill_path.read_text(encoding="utf-8")
    # Check uppercase variant
    skill_path_upper = BUNDLES_DIR / bundle_name / "SKILL.md"
    if skill_path_upper.exists():
        return skill_path_upper.read_text(encoding="utf-8")
    return None


def create_agent_and_session(
    client,
    config: dict,
    model_override: str | None,
    title: str,
    resources: list[dict] | None = None,
    skills: list[dict] | None = None,
    packages: dict[str, list[str]] | None = None,
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
    # Attach skills to the agent (pre-built and/or custom)
    if skills:
        create_params["skills"] = skills

    agent = client.beta.agents.create(**create_params)

    # Build environment config with optional packages
    env_config: dict = {
        "type": "cloud",
        "networking": {"type": "unrestricted"},
    }
    if packages:
        env_config["packages"] = packages

    env = client.beta.environments.create(
        name=f"bundle-{agent_config['name']}-{int(time.time())}",
        config=env_config,
    )

    session_params: dict = {
        "agent": agent.id,
        "environment_id": env.id,
        "title": title,
    }
    if resources:
        session_params["resources"] = resources

    session = client.beta.sessions.create(**session_params)
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


def list_session_files(client, session_id: str) -> list[dict]:
    """セッションのリソース一覧からファイルを抽出する。"""
    try:
        resources = client.beta.sessions.resources.list(session_id=session_id)
        files = []
        for res in resources.data:
            if res.type == "file":
                files.append({
                    "file_id": res.file_id,
                    "mount_path": res.mount_path,
                })
        return files
    except Exception:
        return []


def list_session_output_files(client, session_id: str) -> list[dict]:
    """Files API で session に紐づく出力ファイルを取得する。

    scope_id パラメータでセッション ID を指定し、Agent が生成したファイルを列挙する。
    """
    try:
        result = client.beta.files.list(scope_id=session_id)
        files = []
        for f in result.data:
            files.append({
                "file_id": f.id,
                "filename": f.filename,
                "size_bytes": f.size_bytes,
                "mime_type": f.mime_type,
            })
        return files
    except Exception:
        return []


def download_file_content(client, file_id: str) -> bytes | None:
    """Files API でファイル内容をダウンロードする。"""
    try:
        return client.beta.files.download(file_id)
    except Exception:
        return None


def parse_qa_result(response: str) -> dict:
    """QA Agent のレスポンスから JSON 結果をパースする。"""
    import re

    # Try shared extract + lenient parse first
    try:
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        from agent_factory.utils import extract_json, parse_json_lenient

        json_str = extract_json(response)
        return parse_json_lenient(json_str)
    except (ImportError, ValueError, json.JSONDecodeError):
        pass

    # Fallback: JSON block extraction with plain json.loads
    json_match = re.search(r"```(?:json)?\s*\n(.*?)\n```", response, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass

    # Fallback: parse entire response
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        pass

    # Parse failure
    return {
        "score": 0.0,
        "passed": False,
        "summary": "QA Agent のレスポンスを JSON としてパースできませんでした",
        "feedback": response[:500],
        "parse_error": True,
    }


def build_skill_preamble(skill_content: str) -> str:
    """SKILL.md の内容をプロンプト前文として整形する。"""
    return (
        "## タスク実行スキル（SKILL.md）\n\n"
        "以下はこのタスクの実行に関する詳細なガイダンスです。"
        "これに従って作業してください。\n\n"
        f"{skill_content}\n\n"
        "---\n\n"
    )


def build_feedback_history(feedback_entries: list[dict]) -> str:
    """蓄積されたフィードバック履歴を整形する。"""
    if not feedback_entries:
        return ""
    lines = ["## 過去の QA フィードバック履歴\n"]
    for entry in feedback_entries:
        lines.append(
            f"### ラウンド #{entry['iteration']} "
            f"(スコア: {entry['score']:.2f})\n"
        )
        lines.append(f"{entry['feedback']}\n")
    return "\n".join(lines)


def run_bundle(
    bundle_name: str,
    user_input: str,
    model: str | None = None,
    dry_run: bool = False,
    verbose: bool = False,
) -> dict:
    """バンドルワークフローを実行する。"""
    bundle = load_bundle(bundle_name)

    print(f"=== Bundle 実行: {bundle_name} ===")
    print(f"  Task Agent: {bundle['task_agent']['name']}")
    print(f"  QA Agent:   {bundle['qa_agent']['name']}")
    print(f"  Max QA iterations: {bundle['workflow']['qa']['max_iterations']}")
    print(f"  Pass threshold:    {bundle['workflow']['qa']['pass_threshold']}")

    # ── Phase A: Pre-task ──
    workflow = bundle["workflow"]
    pre_task = workflow.get("pre_task", {})

    skill_content = None
    if pre_task.get("read_skills", True):
        skill_content = load_skill_md(bundle_name)
        if skill_content:
            print(f"  SKILL.md: 読み込み済み ({len(skill_content)} chars)")
        elif verbose:
            print("  SKILL.md: なし")

    # Load skills and environment from bundle.json
    bundle_skills = bundle.get("skills", [])
    bundle_env = bundle.get("environment", {})
    bundle_packages = bundle_env.get("packages", {})
    # Filter out empty package lists
    bundle_packages = {k: v for k, v in bundle_packages.items() if v}

    if bundle_skills:
        skill_ids = [s.get("skill_id", "") for s in bundle_skills]
        print(f"  Skills: {', '.join(skill_ids)}")
    if bundle_packages:
        pkg_strs = [f"{m}: {', '.join(p)}" for m, p in bundle_packages.items()]
        print(f"  Packages: {'; '.join(pkg_strs)}")

    if verbose and pre_task.get("verify_packages"):
        print(f"  verify_packages: {pre_task['verify_packages']}")

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
        if skill_content:
            print(f"\n  [dry-run] SKILL.md: {len(skill_content)} chars")
        if bundle_skills:
            print(f"  [dry-run] Skills: {[s.get('skill_id') for s in bundle_skills]}")
        if bundle_packages:
            print(f"  [dry-run] Packages: {bundle_packages}")
        print()
        print("  [dry-run] ワークフロー検証完了。API 呼び出しはスキップしました。")
        return {"dry_run": True, "status": "ok"}

    # API key check
    check_api_key()
    import anthropic

    client = anthropic.Anthropic()

    task_config = load_agent_config(bundle["task_agent"]["name"])
    qa_config = load_agent_config(bundle["qa_agent"]["name"])
    qa_settings = workflow["qa"]

    results = {
        "bundle": bundle_name,
        "input": user_input,
        "model_override": model,
        "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "skill_injected": skill_content is not None,
        "skills_attached": [s.get("skill_id") for s in bundle_skills],
        "packages_installed": bundle_packages,
        "iterations": [],
        "best_iteration": None,
        "best_score": 0.0,
        "final_status": "incomplete",
    }

    # ── Phase B: Task Agent 実行 ──
    print("[Phase B] Task Agent 実行中...")
    task_agent, task_env, task_session = create_agent_and_session(
        client,
        task_config,
        model,
        f"Bundle Task: {bundle_name}",
        skills=bundle_skills or None,
        packages=bundle_packages or None,
    )

    # Build initial prompt with skill preamble
    initial_prompt = ""
    if skill_content:
        initial_prompt += build_skill_preamble(skill_content)
    initial_prompt += user_input

    task_result = send_and_collect(client, task_session.id, initial_prompt)

    if task_result["errors"]:
        print(f"  ERROR: Task Agent でエラー発生: {task_result['errors']}")
        results["final_status"] = "task_agent_error"
        results["task_errors"] = task_result["errors"]
        return results

    print(f"  Task Agent 完了 (tokens: {task_result['usage']})")
    if verbose:
        print(f"  Tool calls: {len(task_result['tool_calls'])}")
        for tc in task_result["tool_calls"]:
            print(f"    - {tc['name']}")

    task_output = task_result["response"]
    task_tool_calls = task_result["tool_calls"]
    task_usage = task_result["usage"]
    best_output = task_output
    best_score = 0.0

    # Collect output files from Task Agent session
    task_output_files = list_session_output_files(client, task_session.id)
    if task_output_files:
        print(f"  出力ファイル: {len(task_output_files)} 件")
        for f in task_output_files:
            print(f"    - {f['filename']} ({f['size_bytes']} bytes)")
    elif verbose:
        print("  出力ファイル: なし")

    results["task_output_files"] = [
        {"filename": f["filename"], "size_bytes": f["size_bytes"]}
        for f in task_output_files
    ]

    # Track feedback history for accumulation
    feedback_history: list[dict] = []

    # ── Phase C: QA Loop ──
    for iteration in range(1, qa_settings["max_iterations"] + 1):
        print(f"\n[Phase C] QA ループ #{iteration}...")

        # Launch QA Agent in fresh-context (new session)
        # Mount Task Agent output files into QA session if available
        qa_resources: list[dict] = []
        for f in task_output_files:
            qa_resources.append({
                "type": "file",
                "file_id": f["file_id"],
                "mount_path": f"/workspace/artifacts/{f['filename']}",
            })

        qa_agent, qa_env, qa_session = create_agent_and_session(
            client,
            qa_config,
            model,
            f"Bundle QA #{iteration}: {bundle_name}",
            resources=qa_resources if qa_resources else None,
        )

        # QA Agent には成果物のみを渡す（タスク実行過程は渡さない = fresh-context）
        qa_prompt_parts = [
            "以下の成果物を品質検査してください。\n\n"
            "## 検査対象の成果物\n\n"
            f"{task_output}\n\n"
        ]

        if task_output_files:
            qa_prompt_parts.append(
                "## 成果物ファイル\n\n"
                "以下のファイルが /workspace/artifacts/ にマウントされています。"
                "内容を確認して品質検査に含めてください。\n\n"
            )
            for f in task_output_files:
                qa_prompt_parts.append(
                    f"- `/workspace/artifacts/{f['filename']}` "
                    f"({f['size_bytes']} bytes, {f['mime_type']})\n"
                )
            qa_prompt_parts.append("\n")

        qa_prompt_parts.append(f"## 元の入力（参考）\n\n{user_input}")

        qa_prompt = "".join(qa_prompt_parts)

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
            "task_response_excerpt": task_output[:EVIDENCE_RESPONSE_LIMIT],
            "task_tool_calls": [tc["name"] for tc in task_tool_calls],
            "task_output_file_count": len(task_output_files),
            "task_usage": task_usage,
            "qa_usage": qa_result["usage"],
        }
        results["iterations"].append(iteration_result)

        print(f"  QA スコア: {score:.2f} (threshold: {qa_settings['pass_threshold']})")
        if verbose and qa_parsed.get("summary"):
            print(f"  QA summary: {qa_parsed['summary'][:200]}")

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

        # Convergence check (compare only against previous *successful* QA score)
        prev_valid_scores = [
            it["score"] for it in results["iterations"][:-1] if "score" in it
        ]
        if prev_valid_scores:
            prev_score = prev_valid_scores[-1]
            delta = abs(score - prev_score)
            if delta <= qa_settings.get("convergence_delta", 0.02):
                print(
                    f"  収束検出"
                    f"（Δ={delta:.3f} <= {qa_settings.get('convergence_delta', 0.02)}）"
                )
                results["final_status"] = "converged"
                break

        # Not passed: accumulate feedback and give to Task Agent
        feedback_text = qa_parsed.get(
            "feedback", "品質が不十分です。改善してください。"
        )
        feedback_history.append({
            "iteration": iteration,
            "score": score,
            "feedback": feedback_text,
        })

        if iteration < qa_settings["max_iterations"]:
            print("  FAIL: フィードバックを Task Agent に渡して修正中...")

            # Build retry prompt with accumulated feedback
            retry_parts = []
            if len(feedback_history) > 1:
                retry_parts.append(build_feedback_history(feedback_history[:-1]))
                retry_parts.append("---\n\n")
            retry_parts.append(
                f"## 最新の QA フィードバック（ラウンド #{iteration}）\n\n"
                f"{feedback_text}\n\n"
            )
            retry_parts.append(
                "上記のフィードバックに基づいて、前回の出力を改善してください。"
            )
            if len(feedback_history) > 1:
                retry_parts.append(
                    "\n\n**注意**: 過去のフィードバック履歴も参照し、"
                    "既に指摘された問題が再発しないようにしてください。"
                )

            retry_prompt = "".join(retry_parts)
            task_result = send_and_collect(
                client, task_session.id, retry_prompt
            )
            if not task_result["errors"]:
                task_output = task_result["response"]
                task_tool_calls = task_result["tool_calls"]
                task_usage = task_result["usage"]
                # Re-collect output files after retry
                task_output_files = list_session_output_files(
                    client, task_session.id
                )
                if verbose and task_output_files:
                    print(f"  更新された出力ファイル: {len(task_output_files)} 件")
    else:
        results["final_status"] = "max_iterations_reached"

    results["completed_at"] = datetime.datetime.now(
        datetime.timezone.utc
    ).isoformat()
    results["feedback_history"] = [
        {"iteration": fh["iteration"], "score": fh["score"]}
        for fh in feedback_history
    ]

    # ── Phase D: 証跡保存 ──
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    model_label = model or "default"
    evidence_path = (
        EVIDENCE_DIR / f"{timestamp}_{bundle_name}_{model_label}.json"
    )
    with open(evidence_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"\n=== Bundle 実行完了 ===")
    print(f"  最終ステータス: {results['final_status']}")
    print(
        f"  ベストスコア:   {best_score:.2f} "
        f"(iteration #{results.get('best_iteration', 'N/A')})"
    )
    if feedback_history:
        print(f"  フィードバック蓄積: {len(feedback_history)} 回")
    print(f"  証跡: {evidence_path}")

    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bundle ワークフロー実行エンジン v2"
    )
    parser.add_argument("bundle_name", help="バンドル名")
    parser.add_argument(
        "--input", required=False, help="Task Agent への入力"
    )
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
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="詳細なデバッグログを出力する",
    )
    args = parser.parse_args()

    if not args.dry_run and not args.input:
        parser.error("--input は必須です（--dry-run 時を除く）")

    run_bundle(
        bundle_name=args.bundle_name,
        user_input=args.input or "",
        model=args.model,
        dry_run=args.dry_run,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    main()
