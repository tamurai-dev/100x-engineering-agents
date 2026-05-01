"""
共通ユーティリティ — Agent Factory / Bundle Factory 共有関数

LLM 出力の JSON パース、テキスト抽出など、複数モジュールで
共通利用する関数を集約する。
"""

from __future__ import annotations

import json
import re


def extract_json(text: str) -> str:
    """テキストから JSON ブロックを抽出する。

    ```json ... ``` 記法、またはベア JSON（最初の { から最後の }）を抽出。

    Raises:
        ValueError: JSON ブロックが見つからない場合。
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
    """JSON パースを試み、失敗時はよくある LLM 出力エラーを修正してリトライする。

    修正対象:
      - trailing comma before } or ]
      - truncated JSON (unclosed delimiters)
    """
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Trailing commas before } or ]
    cleaned = re.sub(r",\s*([}\]])", r"\1", text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Truncated JSON: close open delimiters in reverse stack order
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
