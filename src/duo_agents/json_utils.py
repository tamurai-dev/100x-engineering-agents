"""JSON helpers for parsing LLM output.

Two utilities used across the project:

* :func:`extract_json` — pull a JSON block out of free-form LLM text
  (handles ```json fenced blocks and bare ``{ ... }`` payloads).
* :func:`parse_json_lenient` — :func:`json.loads` that retries after
  fixing common LLM output mistakes (trailing commas, unclosed
  brackets).

Originally lived in ``scripts/agent_factory/utils.py``. Moved to the
``duo_agents`` package in PR-3 so the helpers survive the AgentFactory
removal that follows.
"""

from __future__ import annotations

import json
import re


def extract_json(text: str) -> str:
    """Return the JSON substring of ``text``.

    Looks for a fenced ```json ... ``` block first, then falls back to
    the slice between the first ``{`` and the last ``}``.

    Raises:
        ValueError: If no JSON-shaped substring can be located.
    """
    match = re.search(r"```json\s*\n(.*?)\n\s*```", text, re.DOTALL)
    if match:
        return match.group(1)

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        return text[start : end + 1]

    raise ValueError(f"JSON が見つかりません:\n{text[:500]}")


def parse_json_lenient(text: str) -> dict:
    """Parse ``text`` as JSON, repairing common LLM output mistakes.

    Currently fixes:

    * Trailing commas before ``}`` / ``]``.
    * Truncated JSON (unclosed brackets / braces).
    """
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Trailing commas before ``}`` or ``]``.
    cleaned = re.sub(r",\s*([}\]])", r"\1", text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Truncated JSON: close open delimiters in reverse stack order.
    fixed = cleaned.rstrip().rstrip(",")
    stack: list[str] = []
    in_string = False
    escape = False
    for ch in fixed:
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch in ("{", "["):
            stack.append("}" if ch == "{" else "]")
        elif ch in ("}", "]") and stack:
            stack.pop()
    fixed += "".join(reversed(stack))
    return json.loads(fixed)


__all__ = ["extract_json", "parse_json_lenient"]
