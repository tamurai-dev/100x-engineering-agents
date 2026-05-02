#!/usr/bin/env python3
"""
Duet ワークフロー実行エンジン v2

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
  - Multiagent Sessions 対応（共有ファイルシステムでの Actor-Critic）

Usage:
    python scripts/run-duet.py <duet-name> --input "レビュー対象コード"
    python scripts/run-duet.py <duet-name> --input "..." --model haiku
    python scripts/run-duet.py <duet-name> --input "..." --verbose
    python scripts/run-duet.py <duet-name> --input "..." --multiagent
    python scripts/run-duet.py <duet-name> --dry-run

環境変数:
    ANTHROPIC_API_KEY  — Anthropic API キー（--dry-run 以外は必須）
"""

from __future__ import annotations

import datetime
import json
import os
import sys
import time
from enum import Enum
from pathlib import Path
from typing import Annotated

import typer


class ModelChoice(str, Enum):
    """Available model tiers."""
    haiku = "haiku"
    sonnet = "sonnet"
    opus = "opus"


REPO_ROOT = Path(__file__).resolve().parent.parent
DUETS_DIR = REPO_ROOT / "agents" / "duets"
AGENTS_DIR = REPO_ROOT / "agents" / "agents"
EVIDENCE_DIR = REPO_ROOT / "evidence" / "duets"

MODEL_MAP = {
    "haiku": "claude-haiku-4-5",
    "sonnet": "claude-sonnet-4-6",
    "opus": "claude-opus-4-6",
}

BETA_HEADER = "managed-agents-2026-04-01"
FILES_BETA = "files-api-2025-04-14"
SKILLS_BETA = "skills-2025-10-02"
MULTIAGENT_BETA = "multiagent-2026-04-01"

# Default model escalation order and threshold
DEFAULT_MODEL_ESCALATION = ["haiku", "sonnet"]
DEFAULT_ESCALATION_THRESHOLD = 0.40
ESCALATION_IMPROVEMENT_DELTA = 0.05

# Max chars of task_response to store in evidence
EVIDENCE_RESPONSE_LIMIT = 2000

# QA loop iteration limit for orchestrator prompt
ORCHESTRATOR_MAX_QA_PROMPT_CHARS = 4000

# artifact_format values that require higher-tier models by default
FORMAT_REQUIRES_SONNET = {"presentation", "structured_data", "media_image"}

# File output instructions appended to Task Agent prompt
FILE_OUTPUT_INSTRUCTIONS = (
    "\n\n---\n"
    "## IMPORTANT: File Output Rules\n\n"
    "1. Save ALL generated artifacts to `/mnt/session/outputs/`.\n"
    "2. After saving, run `ls -la /mnt/session/outputs/` to verify "
    "the files exist and are non-empty.\n"
    "3. If a file is missing or empty, regenerate and save it again.\n"
    "4. Do NOT just describe what you would create — actually create "
    "the files and save them to the output directory.\n"
)


def check_api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        print("ERROR: ANTHROPIC_API_KEY が設定されていません")
        print("  export ANTHROPIC_API_KEY='sk-ant-...'")
        sys.exit(1)
    return key


def load_duet(duet_name: str) -> dict:
    """duet.json を読み込む。"""
    duet_path = DUETS_DIR / duet_name / "duet.json"
    if not duet_path.exists():
        print(f"ERROR: デュエットが見つかりません: {duet_path}")
        sys.exit(1)
    with open(duet_path, encoding="utf-8") as f:
        return json.load(f)


def load_agent_config(agent_name: str) -> dict:
    """エージェントの config.json を読み込む。"""
    config_path = AGENTS_DIR / agent_name / "config.json"
    if not config_path.exists():
        print(f"ERROR: エージェント設定が見つかりません: {config_path}")
        sys.exit(1)
    with open(config_path, encoding="utf-8") as f:
        return json.load(f)


def load_skill_md(duet_name: str) -> str | None:
    """デュエットの SKILL.md を読み込む（存在する場合）。"""
    skill_path = DUETS_DIR / duet_name / "skill.md"
    if skill_path.exists():
        return skill_path.read_text(encoding="utf-8")
    # Check uppercase variant
    skill_path_upper = DUETS_DIR / duet_name / "SKILL.md"
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
        name=f"duet-{agent_config['name']}-{int(time.time())}",
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
        from duo_agents.json_utils import extract_json, parse_json_lenient

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


def build_orchestrator_system(
    duet_name: str,
    qa_settings: dict,
    skill_content: str | None,
) -> str:
    """Build system prompt for the orchestrator agent in multiagent mode."""
    max_iters = qa_settings["max_iterations"]
    pass_threshold = qa_settings["pass_threshold"]
    convergence_delta = qa_settings.get("convergence_delta", 0.02)
    escalation_threshold = qa_settings.get(
        "escalation_threshold", DEFAULT_ESCALATION_THRESHOLD
    )

    parts = [
        f"You are a Duet Orchestrator for '{duet_name}'.\n\n",
        "## Workflow\n\n",
        "1. Delegate the user's task to the **Task Agent**.\n",
        "2. After the Task Agent finishes, delegate QA to the **QA Agent** "
        "with the task output as input. The QA Agent must evaluate the "
        "actual files in /mnt/session/outputs/ (shared filesystem).\n",
        "3. Parse the QA Agent's JSON response to extract `score` and "
        "`feedback`.\n",
        f"4. If score >= {pass_threshold}, report PASS and stop.\n",
        f"5. If score <= {escalation_threshold} and no improvement "
        "(delta < 0.05), note that model escalation is recommended.\n",
        f"6. Otherwise, send the QA feedback to the Task Agent "
        "and repeat from step 2.\n",
        f"7. Maximum {max_iters} QA iterations. "
        f"Stop if convergence detected (delta <= {convergence_delta}).\n\n",
        "## Rules\n\n",
        "- The Task Agent and QA Agent share the same filesystem. "
        "Files saved by Task Agent at /mnt/session/outputs/ are directly "
        "readable by QA Agent.\n",
        "- Always delegate — never perform the task or QA yourself.\n",
        "- Report the final status as a JSON block at the end:\n",
        "```json\n",
        '{"final_status": "passed|max_iterations_reached|converged", '
        '"best_score": 0.0, "iterations_completed": 0}\n',
        "```\n",
    ]

    if skill_content:
        parts.append(
            "\n## SKILL.md (pass to Task Agent)\n\n"
            "When delegating to the Task Agent, include the following "
            "skill guidance in your message:\n\n"
            f"{skill_content[:ORCHESTRATOR_MAX_QA_PROMPT_CHARS]}\n"
        )

    return "".join(parts)


def create_multiagent_session(
    client,
    task_config: dict,
    qa_config: dict,
    duet_name: str,
    qa_settings: dict,
    current_model: str,
    skill_content: str | None = None,
    skills: list[dict] | None = None,
    packages: dict[str, list[str]] | None = None,
) -> tuple:
    """Create orchestrator + callable agents for multiagent mode.

    All agents share the same container and filesystem.
    Returns (orchestrator_agent, task_agent, qa_agent, environment, session).
    """
    # Task Agent
    task_create = {
        "name": task_config["name"],
        "model": MODEL_MAP.get(current_model, current_model),
        "system": task_config.get("system", ""),
    }
    if task_config.get("description"):
        task_create["description"] = task_config["description"]
    if task_config.get("tools"):
        task_create["tools"] = task_config["tools"]
    if skills:
        task_create["skills"] = skills

    task_agent = client.beta.agents.create(**task_create)

    # QA Agent
    qa_create = {
        "name": qa_config["name"],
        "model": qa_config.get("model", MODEL_MAP["sonnet"]),
        "system": qa_config.get("system", ""),
    }
    if qa_config.get("description"):
        qa_create["description"] = qa_config["description"]
    if qa_config.get("tools"):
        qa_create["tools"] = qa_config["tools"]

    qa_agent = client.beta.agents.create(**qa_create)

    # Orchestrator — delegates to both
    orchestrator_system = build_orchestrator_system(
        duet_name, qa_settings, skill_content
    )
    # callable_agents is a Research Preview parameter — pass via extra_body
    # to support SDK versions that don't have it as a named parameter yet.
    orchestrator = client.beta.agents.create(
        name=f"orchestrator-{duet_name}",
        model=MODEL_MAP.get(current_model, current_model),
        system=orchestrator_system,
        tools=[{"type": "agent_toolset_20260401"}],
        betas=[MULTIAGENT_BETA],
        extra_body={
            "callable_agents": [
                {
                    "type": "agent",
                    "id": task_agent.id,
                    "version": task_agent.version,
                },
                {
                    "type": "agent",
                    "id": qa_agent.id,
                    "version": qa_agent.version,
                },
            ],
        },
    )

    # Shared environment
    env_config: dict = {
        "type": "cloud",
        "networking": {"type": "unrestricted"},
    }
    if packages:
        env_config["packages"] = packages

    env = client.beta.environments.create(
        name=f"multiagent-{duet_name}-{int(time.time())}",
        config=env_config,
    )

    session = client.beta.sessions.create(
        agent=orchestrator.id,
        environment_id=env.id,
        title=f"Multiagent Duet: {duet_name}",
    )

    return orchestrator, task_agent, qa_agent, env, session


def collect_multiagent_events(
    client, session_id: str, prompt: str | None = None
) -> dict:
    """Stream events from an orchestrator session and collect results.

    The orchestrator internally delegates to Task and QA agents.
    We collect the final orchestrator response.

    If prompt is provided, opens the stream first then sends the message
    to avoid race conditions (matching send_and_collect pattern).
    """
    messages: list[str] = []
    tool_calls: list[dict] = []
    agent_delegations: list[dict] = []
    errors: list[str] = []

    try:
        with client.beta.sessions.events.stream(session_id) as stream:
            if prompt:
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
                    case "agent.delegation_start":
                        agent_delegations.append({
                            "agent_name": (
                                event.agent_name
                                if hasattr(event, "agent_name")
                                else "unknown"
                            ),
                            "status": "started",
                        })
                    case "agent.delegation_end":
                        if agent_delegations:
                            agent_delegations[-1]["status"] = "completed"
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
        "agent_delegations": agent_delegations,
        "errors": errors,
        "usage": usage,
    }


def run_duet_multiagent(
    duet_name: str,
    user_input: str,
    model: str | None = None,
    verbose: bool = False,
) -> dict:
    """Run duet workflow in multiagent mode.

    The orchestrator agent coordinates Task + QA agents within a single
    shared-filesystem session, solving the file handoff problem.
    """
    duet = load_duet(duet_name)

    print(f"=== Duet 実行 (Multiagent): {duet_name} ===")
    print(f"  Task Agent: {duet['task_agent']['name']}")
    print(f"  QA Agent:   {duet['qa_agent']['name']}")

    workflow = duet["workflow"]
    qa_settings = workflow["qa"]
    pre_task = workflow.get("pre_task", {})

    skill_content = None
    if pre_task.get("read_skills", True):
        skill_content = load_skill_md(duet_name)
        if skill_content:
            print(f"  SKILL.md: 読み込み済み ({len(skill_content)} chars)")

    duet_skills = duet.get("skills", [])
    duet_env = duet.get("environment", {})
    duet_packages = duet_env.get("packages", {})
    duet_packages = {k: v for k, v in duet_packages.items() if v}

    if duet_skills:
        skill_ids = [s.get("skill_id", "") for s in duet_skills]
        print(f"  Skills: {', '.join(skill_ids)}")
    print(f"  Mode: multiagent (shared filesystem)")
    print()

    check_api_key()
    import anthropic

    client = anthropic.Anthropic()

    task_config = load_agent_config(duet["task_agent"]["name"])
    qa_config = load_agent_config(duet["qa_agent"]["name"])

    explicit_model = model is not None
    escalation_order = qa_settings.get(
        "model_escalation", DEFAULT_MODEL_ESCALATION
    )
    current_model = model or escalation_order[0]

    results = {
        "duet": duet_name,
        "input": user_input,
        "mode": "multiagent",
        "model_override": model,
        "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "skill_injected": skill_content is not None,
        "skills_attached": [s.get("skill_id") for s in duet_skills],
        "packages_installed": duet_packages,
        "model_escalation": escalation_order if not explicit_model else None,
        "iterations": [],
        "best_score": 0.0,
        "final_status": "incomplete",
    }

    print(f"[Phase B] Orchestrator 実行中 (model: {current_model})...")

    try:
        orchestrator, task_agent, qa_agent, env, session = (
            create_multiagent_session(
                client,
                task_config,
                qa_config,
                duet_name,
                qa_settings,
                current_model,
                skill_content=skill_content,
                skills=duet_skills or None,
                packages=duet_packages or None,
            )
        )
    except Exception as e:
        err_str = str(e)
        if "callable_agents" in err_str or "Extra inputs" in err_str:
            print(
                "\n  ERROR: Multiagent Sessions は Research Preview 機能です。"
                "\n  Anthropic に Research Preview アクセスを申請してください。"
                "\n  https://docs.anthropic.com/en/docs/agents-and-tools/"
                "managed-agents/multiagent-sessions"
                "\n\n  代替: --multiagent なしで従来モード（別セッション方式）"
                "を使用できます。\n"
            )
        else:
            print(f"\n  ERROR: セッション作成失敗: {e}\n")
        results["final_status"] = "multiagent_not_available"
        results["error"] = err_str
        results["completed_at"] = datetime.datetime.now(
            datetime.timezone.utc
        ).isoformat()
        # Save partial evidence
        EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y-%m-%d"
        )
        model_label = model or "default"
        evidence_path = (
            EVIDENCE_DIR
            / f"{timestamp}_{duet_name}_multiagent_{model_label}.json"
        )
        with open(evidence_path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print(f"  証跡: {evidence_path}")
        return results

    # Send user task to orchestrator — it will delegate internally
    orchestrator_prompt = (
        f"## Task\n\n{user_input}\n\n"
        "Please delegate this task to the Task Agent, then have the "
        "QA Agent evaluate the results. Follow the workflow in your "
        "system prompt."
    )

    # Open stream first, then send message to avoid race condition
    result = collect_multiagent_events(client, session.id, orchestrator_prompt)

    if result["errors"]:
        print(f"  ERROR: Orchestrator でエラー発生: {result['errors']}")
        results["final_status"] = "orchestrator_error"
        results["errors"] = result["errors"]
    else:
        print(f"  Orchestrator 完了 (tokens: {result['usage']})")
        if verbose:
            print(f"  Delegations: {len(result['agent_delegations'])}")
            for d in result["agent_delegations"]:
                print(f"    - {d['agent_name']}: {d['status']}")

        # Parse final result from orchestrator response
        orchestrator_result = parse_qa_result(result["response"])
        results["final_status"] = orchestrator_result.get(
            "final_status", "unknown"
        )
        results["best_score"] = orchestrator_result.get("best_score", 0.0)
        results["orchestrator_response_excerpt"] = result["response"][
            :EVIDENCE_RESPONSE_LIMIT
        ]
        results["agent_delegations"] = result["agent_delegations"]

    results["completed_at"] = datetime.datetime.now(
        datetime.timezone.utc
    ).isoformat()

    # Collect session threads for evidence
    try:
        threads = client.beta.sessions.threads.list(session.id)
        results["threads"] = [
            {
                "agent_name": t.agent_name,
                "status": t.status,
            }
            for t in threads.data
        ]
    except Exception:
        results["threads"] = []

    # Evidence
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    model_label = model or "default"
    evidence_path = (
        EVIDENCE_DIR / f"{timestamp}_{duet_name}_multiagent_{model_label}.json"
    )
    with open(evidence_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"\n=== Duet 実行完了 (Multiagent) ===")
    print(f"  最終ステータス: {results['final_status']}")
    print(f"  ベストスコア:   {results['best_score']}")
    if result.get("agent_delegations"):
        print(f"  Agent 委譲回数: {len(result['agent_delegations'])}")
    print(f"  証跡: {evidence_path}")

    return results


def should_escalate_model(
    current_model: str,
    score: float,
    prev_score: float | None,
    escalation_order: list[str],
    threshold: float,
) -> str | None:
    """Determine whether to escalate to a higher-tier model.

    Returns the next model name if escalation is needed, None otherwise.
    """
    if score > threshold:
        return None
    if prev_score is not None and (score - prev_score) >= ESCALATION_IMPROVEMENT_DELTA:
        return None
    try:
        idx = escalation_order.index(current_model)
    except ValueError:
        return None
    if idx + 1 >= len(escalation_order):
        return None
    return escalation_order[idx + 1]


def run_duet(
    duet_name: str,
    user_input: str,
    model: str | None = None,
    dry_run: bool = False,
    verbose: bool = False,
) -> dict:
    """デュエットワークフローを実行する。"""
    duet = load_duet(duet_name)

    print(f"=== Duet 実行: {duet_name} ===")
    print(f"  Task Agent: {duet['task_agent']['name']}")
    print(f"  QA Agent:   {duet['qa_agent']['name']}")
    print(f"  Max QA iterations: {duet['workflow']['qa']['max_iterations']}")
    print(f"  Pass threshold:    {duet['workflow']['qa']['pass_threshold']}")

    # ── Phase A: Pre-task ──
    workflow = duet["workflow"]
    pre_task = workflow.get("pre_task", {})

    skill_content = None
    if pre_task.get("read_skills", True):
        skill_content = load_skill_md(duet_name)
        if skill_content:
            print(f"  SKILL.md: 読み込み済み ({len(skill_content)} chars)")
        elif verbose:
            print("  SKILL.md: なし")

    # Load skills and environment from duet.json
    duet_skills = duet.get("skills", [])
    duet_env = duet.get("environment", {})
    duet_packages = duet_env.get("packages", {})
    # Filter out empty package lists
    duet_packages = {k: v for k, v in duet_packages.items() if v}

    if duet_skills:
        skill_ids = [s.get("skill_id", "") for s in duet_skills]
        print(f"  Skills: {', '.join(skill_ids)}")
    if duet_packages:
        pkg_strs = [f"{m}: {', '.join(p)}" for m, p in duet_packages.items()]
        print(f"  Packages: {'; '.join(pkg_strs)}")

    if verbose and pre_task.get("verify_packages"):
        print(f"  verify_packages: {pre_task['verify_packages']}")

    print()

    if dry_run:
        task_config = load_agent_config(duet["task_agent"]["name"])
        qa_config = load_agent_config(duet["qa_agent"]["name"])
        print("  [dry-run] Task Agent config: OK")
        print(f"    model: {task_config.get('model')}")
        print(f"    system: {task_config.get('system', '')[:80]}...")
        print()
        print("  [dry-run] QA Agent config: OK")
        print(f"    model: {qa_config.get('model')}")
        print(f"    system: {qa_config.get('system', '')[:80]}...")
        if skill_content:
            print(f"\n  [dry-run] SKILL.md: {len(skill_content)} chars")
        if duet_skills:
            print(f"  [dry-run] Skills: {[s.get('skill_id') for s in duet_skills]}")
        if duet_packages:
            print(f"  [dry-run] Packages: {duet_packages}")
        print()
        print("  [dry-run] ワークフロー検証完了。API 呼び出しはスキップしました。")
        return {"dry_run": True, "status": "ok"}

    # API key check
    check_api_key()
    import anthropic

    client = anthropic.Anthropic()

    task_config = load_agent_config(duet["task_agent"]["name"])
    qa_config = load_agent_config(duet["qa_agent"]["name"])
    qa_settings = workflow["qa"]

    # Model escalation settings
    escalation_order = qa_settings.get(
        "model_escalation", DEFAULT_MODEL_ESCALATION
    )
    escalation_threshold = qa_settings.get(
        "escalation_threshold", DEFAULT_ESCALATION_THRESHOLD
    )
    # If user explicitly specified a model, disable escalation
    explicit_model = model is not None
    artifact_format = duet.get("artifact_format", "")
    if not explicit_model and artifact_format in FORMAT_REQUIRES_SONNET:
        # Complex artifact formats start with sonnet for higher success rate
        default_model = "sonnet" if "sonnet" in escalation_order else escalation_order[0]
        current_model = default_model
        print(f"  artifact_format '{artifact_format}' -> デフォルト: {default_model}")
    else:
        current_model = model or escalation_order[0]

    results = {
        "duet": duet_name,
        "input": user_input,
        "model_override": model,
        "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "skill_injected": skill_content is not None,
        "skills_attached": [s.get("skill_id") for s in duet_skills],
        "packages_installed": duet_packages,
        "model_escalation": escalation_order if not explicit_model else None,
        "escalation_threshold": escalation_threshold if not explicit_model else None,
        "iterations": [],
        "best_iteration": None,
        "best_score": 0.0,
        "final_status": "incomplete",
    }

    # ── Phase B: Task Agent 実行 ──
    print(f"[Phase B] Task Agent 実行中 (model: {current_model})...")
    task_agent, task_env, task_session = create_agent_and_session(
        client,
        task_config,
        current_model,
        f"Duet Task: {duet_name}",
        skills=duet_skills or None,
        packages=duet_packages or None,
    )

    # Build initial prompt with skill preamble + file output instructions
    initial_prompt = ""
    if skill_content:
        initial_prompt += build_skill_preamble(skill_content)
    initial_prompt += user_input
    initial_prompt += FILE_OUTPUT_INSTRUCTIONS

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
            f"Duet QA #{iteration}: {duet_name}",
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
            "model": current_model,
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

        # Convergence check — only compare scores from the same model
        prev_valid_scores = [
            it["score"]
            for it in results["iterations"][:-1]
            if "score" in it and it.get("model") == current_model
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
            # ── Model escalation check ──
            if not explicit_model:
                prev_score_for_esc = (
                    prev_valid_scores[-1] if prev_valid_scores else None
                )
                next_model = should_escalate_model(
                    current_model,
                    score,
                    prev_score_for_esc,
                    escalation_order,
                    escalation_threshold,
                )
                if next_model:
                    print(
                        f"  ESCALATE: {current_model} → {next_model}"
                        f" (score {score:.2f} <= threshold {escalation_threshold})"
                    )
                    prev_model = current_model
                    prev_task_session = task_session
                    current_model = next_model
                    iteration_result["escalated_to"] = next_model
                    results.setdefault("escalations", []).append({
                        "from": escalation_order[
                            escalation_order.index(next_model) - 1
                        ],
                        "to": next_model,
                        "at_iteration": iteration,
                        "trigger_score": score,
                    })
                    # Re-create Task Agent with upgraded model
                    task_agent, task_env, task_session = (
                        create_agent_and_session(
                            client,
                            task_config,
                            current_model,
                            f"Duet Task (escalated): {duet_name}",
                            skills=duet_skills or None,
                            packages=duet_packages or None,
                        )
                    )
                    # Re-send initial prompt + feedback to new agent
                    escalation_prompt = initial_prompt
                    if feedback_history:
                        escalation_prompt += (
                            "\n\n---\n\n"
                            + build_feedback_history(feedback_history)
                            + "\n上記のフィードバックに基づいて"
                            "高品質な成果物を生成してください。"
                        )
                    task_result = send_and_collect(
                        client, task_session.id, escalation_prompt
                    )
                    if not task_result["errors"]:
                        task_output = task_result["response"]
                        task_tool_calls = task_result["tool_calls"]
                        task_usage = task_result["usage"]
                        task_output_files = list_session_output_files(
                            client, task_session.id
                        )
                        if task_output_files:
                            print(
                                f"  出力ファイル: {len(task_output_files)} 件"
                            )
                    else:
                        # Escalation failed — fall back to previous session
                        print(
                            f"  WARN: エスカレーション先で"
                            f"エラー発生、{prev_model} に復帰"
                        )
                        current_model = prev_model
                        task_session = prev_task_session
                        iteration_result["escalation_failed"] = True
                    continue

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
        EVIDENCE_DIR / f"{timestamp}_{duet_name}_{model_label}.json"
    )
    with open(evidence_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"\n=== Duet 実行完了 ===")
    print(f"  最終ステータス: {results['final_status']}")
    print(
        f"  ベストスコア:   {best_score:.2f} "
        f"(iteration #{results.get('best_iteration', 'N/A')})"
    )
    if feedback_history:
        print(f"  フィードバック蓄積: {len(feedback_history)} 回")
    print(f"  証跡: {evidence_path}")

    return results


app = typer.Typer(add_completion=False, help="Duet ワークフロー実行エンジン v2")


@app.command()
def main(
    duet_name: Annotated[str, typer.Argument(help="デュエット名")],
    input: Annotated[
        str | None,
        typer.Option("--input", help="Task Agent への入力"),
    ] = None,
    model: Annotated[
        ModelChoice | None,
        typer.Option("--model", help="モデルのオーバーライド"),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="API を呼ばずにワークフロー検証のみ実行"),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", help="詳細なデバッグログを出力する"),
    ] = False,
    multiagent: Annotated[
        bool,
        typer.Option("--multiagent", help="Multiagent Sessions モードで実行（共有ファイルシステム）"),
    ] = False,
) -> None:
    """Duet ワークフロー実行エンジン v2。"""
    if not dry_run and not input:
        typer.echo("ERROR: --input は必須です（--dry-run 時を除く）", err=True)
        raise typer.Exit(code=2)

    model_str = model.value if model else None

    if multiagent and not dry_run:
        run_duet_multiagent(
            duet_name=duet_name,
            user_input=input or "",
            model=model_str,
            verbose=verbose,
        )
    else:
        run_duet(
            duet_name=duet_name,
            user_input=input or "",
            model=model_str,
            dry_run=dry_run,
            verbose=verbose,
        )


if __name__ == "__main__":
    app()
