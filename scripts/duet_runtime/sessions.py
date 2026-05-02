"""Managed Agents API のセッション操作。

エージェント作成、メッセージ送受信、ファイルリスト取得、ファイルダウンロード。
"""

from __future__ import annotations

import time

from .constants import MODEL_MAP


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
