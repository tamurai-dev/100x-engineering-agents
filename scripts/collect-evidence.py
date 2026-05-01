#!/usr/bin/env python3
"""
セッション証跡収集ツール

Managed Agents セッションのイベントを取得し、evidence/sessions/ に保存する。
test-agent.py が自動保存するが、既存セッションの手動取得にも使用可能。

Usage:
    python scripts/collect-evidence.py <session-id>                   # セッションイベント取得
    python scripts/collect-evidence.py <session-id> --agent-name xxx  # エージェント名を指定
    python scripts/collect-evidence.py summary                        # SUMMARY.md 再生成

環境変数:
    ANTHROPIC_API_KEY  — Anthropic API キー（summary 以外で必須）
"""

from __future__ import annotations

import datetime
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
EVIDENCE_DIR = REPO_ROOT / "evidence" / "sessions"


def collect_session_events(session_id: str, agent_name: str = "unknown") -> Path:
    """セッションの全イベントを取得して保存する。"""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY が設定されていません")
        sys.exit(1)

    try:
        from anthropic import Anthropic
    except ImportError:
        print("ERROR: anthropic SDK が必要です")
        print("  pip install anthropic")
        sys.exit(1)

    client = Anthropic(api_key=api_key)

    # セッション情報取得
    session = client.beta.sessions.retrieve(session_id)
    usage = {
        "input_tokens": session.usage.input_tokens if hasattr(session, "usage") and session.usage else 0,
        "output_tokens": session.usage.output_tokens if hasattr(session, "usage") and session.usage else 0,
    }

    # 全イベント取得
    events = []
    for event in client.beta.sessions.events.list(session_id):
        event_data = {
            "type": event.type,
            "processed_at": str(event.processed_at) if event.processed_at else None,
        }
        match event.type:
            case "user.message" | "agent.message":
                event_data["content"] = []
                if hasattr(event, "content"):
                    for block in event.content:
                        if hasattr(block, "text"):
                            event_data["content"].append({"type": "text", "text": block.text[:2000]})
            case "agent.tool_use" | "agent.custom_tool_use" | "agent.mcp_tool_use":
                event_data["tool_name"] = event.name if hasattr(event, "name") else "unknown"
                if hasattr(event, "input"):
                    event_data["input_preview"] = str(event.input)[:500]
            case "agent.tool_result":
                if hasattr(event, "content"):
                    event_data["content_preview"] = str(event.content)[:1000]
            case "agent.thinking":
                if hasattr(event, "content"):
                    event_data["thinking_preview"] = str(event.content)[:500]
            case "span.model_request_end":
                if hasattr(event, "model_usage"):
                    event_data["model_usage"] = {
                        "input_tokens": event.model_usage.input_tokens,
                        "output_tokens": event.model_usage.output_tokens,
                    }
            case "session.error":
                if hasattr(event, "error"):
                    event_data["error"] = str(event.error)[:500]
        events.append(event_data)

    # 保存
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    filename = f"{date_str}_{agent_name}_{session_id[:16]}.json"
    filepath = EVIDENCE_DIR / filename

    evidence = {
        "session_id": session_id,
        "agent": agent_name,
        "status": session.status if hasattr(session, "status") else "unknown",
        "date": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "usage": usage,
        "event_count": len(events),
        "events": events,
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(evidence, f, ensure_ascii=False, indent=2)

    print(f"証跡保存: {filepath.relative_to(REPO_ROOT)}")
    print(f"  イベント数: {len(events)}")
    print(f"  トークン: input={usage['input_tokens']}, output={usage['output_tokens']}")
    return filepath


def generate_summary() -> None:
    """evidence/sessions/ の全ファイルから SUMMARY.md を生成する。"""
    summary_path = REPO_ROOT / "evidence" / "SUMMARY.md"

    if not EVIDENCE_DIR.exists():
        EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

    entries = []
    for f in sorted(EVIDENCE_DIR.glob("*.json")):
        try:
            with open(f, encoding="utf-8") as fp:
                data = json.load(fp)
            entries.append({
                "file": f.name,
                "agent": data.get("agent", "unknown"),
                "model": data.get("model", "unknown"),
                "date": data.get("date", "unknown"),
                "summary": data.get("summary", {}),
                "session_id": data.get("session_id", ""),
                "results": data.get("results", []),
            })
        except (json.JSONDecodeError, KeyError):
            continue

    lines = [
        "<!-- このファイルは自動生成です。手動編集しないでください。 -->",
        "<!-- 再生成: python scripts/collect-evidence.py summary -->",
        "",
        "# 証跡サマリー（Managed Agents セッション）",
        "",
        f"最終更新: {datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
    ]

    if not entries:
        lines.append("_証跡なし。`make test-agent NAME=<agent-name>` でテストを実行してください。_")
    else:
        lines.append("| 日付 | エージェント | モデル | テスト数 | 合格 | 不合格 | ファイル |")
        lines.append("|------|------------|--------|---------|------|--------|---------|")

        for entry in entries:
            date = entry["date"][:10] if entry["date"] != "unknown" else "—"
            summary = entry.get("summary", {})
            total = summary.get("total", len(entry.get("results", [])))
            passed = summary.get("passed", 0)
            failed = summary.get("failed", 0)
            model = entry.get("model", "—")
            lines.append(
                f"| {date} | {entry['agent']} | {model} | {total} | {passed} | {failed} | `{entry['file']}` |"
            )

    lines.append("")
    summary_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"SUMMARY.md 更新: {summary_path.relative_to(REPO_ROOT)}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    if sys.argv[1] == "summary":
        generate_summary()
        return

    session_id = sys.argv[1]
    agent_name = "unknown"

    if "--agent-name" in sys.argv:
        idx = sys.argv.index("--agent-name")
        if idx + 1 < len(sys.argv):
            agent_name = sys.argv[idx + 1]

    collect_session_events(session_id, agent_name)


if __name__ == "__main__":
    main()
