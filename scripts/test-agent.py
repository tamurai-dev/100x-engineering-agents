#!/usr/bin/env python3
"""
Managed Agents テストランナー

エージェントの config.json と test-prompts.json を読み込み、
Claude Managed Agents API でテストを実行し、セッションイベントを証跡として保存する。

Usage:
    python scripts/test-agent.py <agent-name>                  # sonnet でテスト
    python scripts/test-agent.py <agent-name> --model haiku    # haiku でテスト
    python scripts/test-agent.py <agent-name> --model all      # haiku → sonnet の2段テスト
    python scripts/test-agent.py --all                         # 全エージェントをテスト
    python scripts/test-agent.py --all --model all             # 全エージェント × 全モデル

環境変数:
    ANTHROPIC_API_KEY  — Anthropic API キー（必須）
"""

from __future__ import annotations

import datetime
import json
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
AGENTS_DIR = REPO_ROOT / "agents" / "agents"
EVIDENCE_DIR = REPO_ROOT / "evidence" / "sessions"

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


def load_config(agent_name: str) -> dict:
    config_path = AGENTS_DIR / agent_name / "config.json"
    if not config_path.exists():
        print(f"ERROR: {config_path} が見つかりません")
        sys.exit(1)
    with open(config_path, encoding="utf-8") as f:
        return json.load(f)


def load_test_prompts(agent_name: str) -> list[dict]:
    prompts_path = AGENTS_DIR / agent_name / "test-prompts.json"
    if not prompts_path.exists():
        print(f"ERROR: {prompts_path} が見つかりません")
        sys.exit(1)
    with open(prompts_path, encoding="utf-8") as f:
        return json.load(f)


def list_agents() -> list[str]:
    agents = []
    for d in sorted(AGENTS_DIR.iterdir()):
        if d.is_dir() and (d / "config.json").exists():
            agents.append(d.name)
    return agents


def run_test(client, config: dict, test_prompt: dict, model_override: str | None = None) -> dict:
    """1つのテストプロンプトを Managed Agents API で実行し、結果を返す。"""

    agent_config = dict(config)
    if model_override:
        agent_config["model"] = MODEL_MAP.get(model_override, model_override)

    # Security screening (input) — run before API resource creation
    from scripts.security import screen_text
    from scripts.security.config import SecurityConfig

    security_config = SecurityConfig.load()
    security_data: dict = {"provider": "noop"}
    if security_config.should_screen("test_agent", "input"):
        input_screening = screen_text(
            test_prompt["prompt"],
            direction="input",
            metadata={"context": "test_agent", "agent": agent_config["name"]},
        )
        security_data["input"] = input_screening.to_dict()
        security_data["provider"] = input_screening.provider
        if not input_screening.safe_to_proceed:
            return {
                "test_name": test_prompt["name"],
                "model": agent_config["model"],
                "agent_id": None,
                "session_id": None,
                "environment_id": None,
                "status": "blocked_by_security",
                "response_preview": security_config.messages.get("blocked", ""),
                "tool_calls": [],
                "expected_behaviors": test_prompt.get("expected_behaviors", []),
                "matched_behaviors": [],
                "errors": ["Security screening blocked this input"],
                "usage": {"input_tokens": 0, "output_tokens": 0},
                "events": [],
                "security": security_data,
            }

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
        name=f"test-{agent_config['name']}-{int(time.time())}",
        config={"type": "cloud", "networking": {"type": "unrestricted"}},
    )

    # セッション作成
    session = client.beta.sessions.create(
        agent=agent.id,
        environment_id=env.id,
        title=f"Test: {test_prompt['name']}",
    )

    # プロンプト送信 & ストリーミング
    messages = []
    tool_calls = []
    errors = []

    try:
        with client.beta.sessions.events.stream(session.id) as stream:
            client.beta.sessions.events.send(
                session.id,
                events=[
                    {
                        "type": "user.message",
                        "content": [{"type": "text", "text": test_prompt["prompt"]}],
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
                        errors.append(str(event.error.message) if hasattr(event, "error") else "unknown error")
                    case "session.status_idle":
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
        event_data = {"type": event.type, "processed_at": str(event.processed_at) if event.processed_at else None}
        match event.type:
            case "agent.message":
                event_data["content"] = [block.text for block in event.content if hasattr(block, "text")]
            case "agent.tool_use" | "agent.custom_tool_use" | "agent.mcp_tool_use":
                event_data["tool_name"] = event.name
            case "agent.tool_result":
                if hasattr(event, "content"):
                    event_data["content_preview"] = str(event.content)[:500]
            case "span.model_request_end":
                if hasattr(event, "model_usage"):
                    event_data["model_usage"] = {
                        "input_tokens": event.model_usage.input_tokens,
                        "output_tokens": event.model_usage.output_tokens,
                    }
        all_events.append(event_data)

    # 成功判定
    full_response = "\n".join(messages)
    expected = test_prompt.get("expected_behaviors", [])
    matched = []
    for behavior in expected:
        resp_lower = full_response.lower()
        # exact substring match
        if behavior.lower() in resp_lower:
            matched.append(behavior)
            continue
        # split on Japanese particles and check if enough keywords match
        particles = ["の", "が", "を", "に", "で", "は", "と", "も", "から", "まで", "より"]
        keywords = [behavior]
        for p in particles:
            new_keywords = []
            for kw in keywords:
                new_keywords.extend(kw.split(p))
            keywords = new_keywords
        keywords = [kw.strip() for kw in keywords if len(kw.strip()) >= 2]
        if keywords:
            hit_count = sum(1 for kw in keywords if kw.lower() in resp_lower)
            if hit_count >= max(1, len(keywords) // 2):
                matched.append(behavior)

    # Security screening (output)
    if security_config.should_screen("test_agent", "output"):
        output_screening = screen_text(
            full_response,
            direction="output",
            metadata={"context": "test_agent", "agent": agent_config["name"]},
        )
        security_data["output"] = output_screening.to_dict()
        security_data["provider"] = output_screening.provider

    result = {
        "test_name": test_prompt["name"],
        "model": agent_config["model"],
        "agent_id": agent.id,
        "session_id": session.id,
        "environment_id": env.id,
        "status": "pass" if not errors and len(matched) > 0 else "fail",
        "response_preview": full_response[:2000],
        "tool_calls": tool_calls,
        "expected_behaviors": expected,
        "matched_behaviors": matched,
        "errors": errors,
        "usage": usage,
        "events": all_events,
        "security": security_data,
    }

    return result


def save_evidence(agent_name: str, model: str, results: list[dict]) -> Path:
    """テスト結果を evidence/sessions/ に保存する。"""
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

    date_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    filename = f"{date_str}_{agent_name}_{model}.json"
    filepath = EVIDENCE_DIR / filename

    evidence = {
        "agent": agent_name,
        "model": model,
        "date": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "results": results,
        "summary": {
            "total": len(results),
            "passed": sum(1 for r in results if r["status"] == "pass"),
            "failed": sum(1 for r in results if r["status"] == "fail"),
            "blocked": sum(1 for r in results if r["status"] == "blocked_by_security"),
        },
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(evidence, f, ensure_ascii=False, indent=2)

    return filepath


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Managed Agents テストランナー")
    parser.add_argument("agent_name", nargs="?", help="テスト対象エージェント名")
    parser.add_argument("--all", action="store_true", help="全エージェントをテスト")
    parser.add_argument("--model", default="sonnet", help="テストモデル: haiku, sonnet, opus, all")
    parser.add_argument("--dry-run", action="store_true", help="API を呼ばずに設定のみ確認")
    args = parser.parse_args()

    if not args.agent_name and not args.all:
        parser.print_help()
        sys.exit(1)

    agents = list_agents() if args.all else [args.agent_name]
    models = ["haiku", "sonnet"] if args.model == "all" else [args.model]

    if args.dry_run:
        print("=== ドライラン ===")
        for agent_name in agents:
            config = load_config(agent_name)
            prompts = load_test_prompts(agent_name)
            print(f"\n{agent_name}:")
            print(f"  config.json: OK (model={config['model']})")
            print(f"  test-prompts: {len(prompts)} テストケース")
            for m in models:
                print(f"  テスト実行予定: {m} ({MODEL_MAP.get(m, m)})")
        return

    api_key = check_api_key()

    try:
        from anthropic import Anthropic
    except ImportError:
        print("ERROR: anthropic SDK が必要です")
        print("  pip install anthropic")
        sys.exit(1)

    client = Anthropic(api_key=api_key)

    total_passed = 0
    total_failed = 0
    total_blocked = 0

    for agent_name in agents:
        config = load_config(agent_name)
        prompts = load_test_prompts(agent_name)

        for model in models:
            print(f"\n{'='*60}")
            print(f"  {agent_name} / {model} ({MODEL_MAP.get(model, model)})")
            print(f"{'='*60}")

            results = []
            for prompt in prompts:
                print(f"\n  テスト: {prompt['name']} ...", end=" ", flush=True)
                try:
                    result = run_test(client, config, prompt, model_override=model)
                    results.append(result)
                    status = "PASS" if result["status"] == "pass" else "FAIL"
                    print(f"{status}")
                    if result["errors"]:
                        for err in result["errors"]:
                            print(f"    ERROR: {err}")
                except Exception as e:
                    print(f"ERROR: {e}")
                    results.append({
                        "test_name": prompt["name"],
                        "model": MODEL_MAP.get(model, model),
                        "status": "fail",
                        "errors": [str(e)],
                    })

            filepath = save_evidence(agent_name, model, results)
            passed = sum(1 for r in results if r["status"] == "pass")
            failed = sum(1 for r in results if r["status"] == "fail")
            blocked = sum(1 for r in results if r["status"] == "blocked_by_security")
            total_passed += passed
            total_failed += failed
            total_blocked += blocked

            print(f"\n  結果: {passed}/{len(results)} PASS")
            if blocked > 0:
                print(f"  ブロック: {blocked}")
            print(f"  証跡: {filepath.relative_to(REPO_ROOT)}")

    print(f"\n{'='*60}")
    print(f"  合計: {total_passed} passed / {total_failed} failed")
    if total_blocked > 0:
        print(f"  ブロック: {total_blocked}")
    print(f"{'='*60}")
    sys.exit(1 if total_failed > 0 or total_blocked > 0 else 0)


if __name__ == "__main__":
    main()
