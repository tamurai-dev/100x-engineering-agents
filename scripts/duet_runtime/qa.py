"""QA レスポンスのパース、フィードバック整形、モデルエスカレーション判定。"""

from __future__ import annotations

import json
import re

from .constants import ESCALATION_IMPROVEMENT_DELTA


def parse_qa_result(response: str) -> dict:
    """QA Agent のレスポンスから JSON 結果をパースする。"""
    # Try shared extract + lenient parse first
    try:
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
