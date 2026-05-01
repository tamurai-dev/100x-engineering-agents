"""
Model-Based Grader

Messages API を使ったルーブリック採点。
Managed Agents セッションではなく 1 回の Messages API 呼び出しで完結する。
"""

from __future__ import annotations

import json
from pathlib import Path


GRADER_SYSTEM_PROMPT = """\
あなたはエージェント出力の品質を評価する採点者です。

与えられたルーブリックに基づいて、エージェントの出力を採点してください。

## 採点ルール

1. 各基準ごとに 0.0〜1.0 のスコアを付けてください
2. スコアの根拠を簡潔に説明してください
3. 必ず以下の JSON 形式で回答してください（他のテキストは不要）:

```json
{
  "criteria": [
    {
      "name": "基準名",
      "score": 0.85,
      "reason": "根拠の説明"
    }
  ],
  "overall_score": 0.82,
  "summary": "総合評価の一言コメント"
}
```
"""


def grade_with_rubric(
    client,
    agent_output: str,
    rubric_path: Path,
    task_prompt: str = "",
    model: str = "claude-haiku-4-5",
) -> dict:
    """
    ルーブリックに基づいてエージェント出力を採点する。

    Messages API の 1 回呼び出しで完結。Managed Agents セッションは不要。

    Args:
        client: Anthropic client
        agent_output: エージェントの出力テキスト
        rubric_path: rubric.md のパス
        task_prompt: 元のタスクプロンプト（採点の文脈として提供）
        model: grader に使うモデル

    Returns:
        {
            "rubric_score": float,
            "criteria": [...],
            "summary": str,
            "grader_model": str,
            "raw_response": str
        }
    """
    rubric_text = rubric_path.read_text(encoding="utf-8")

    user_message = f"""## タスクプロンプト（エージェントへの指示）
{task_prompt}

## ルーブリック（採点基準）
{rubric_text}

## エージェント出力（採点対象）
{agent_output[:8000]}
"""

    try:
        response = client.messages.create(
            model=model,
            max_tokens=2000,
            system=GRADER_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )

        raw_text = response.content[0].text
        parsed = _parse_grader_response(raw_text)

        return {
            "rubric_score": parsed.get("overall_score", 0.0),
            "criteria": parsed.get("criteria", []),
            "summary": parsed.get("summary", ""),
            "grader_model": model,
            "grader_tokens": {
                "input": response.usage.input_tokens,
                "output": response.usage.output_tokens,
            },
        }
    except Exception as e:
        return {
            "rubric_score": 0.0,
            "criteria": [],
            "summary": f"Grader error: {e}",
            "grader_model": model,
            "error": str(e),
        }


def _parse_grader_response(text: str) -> dict:
    """grader の JSON レスポンスをパースする。"""
    json_match = None
    if "```json" in text:
        start = text.index("```json") + 7
        end = text.index("```", start)
        json_match = text[start:end].strip()
    elif "```" in text:
        start = text.index("```") + 3
        end = text.index("```", start)
        json_match = text[start:end].strip()
    else:
        brace_start = text.find("{")
        brace_end = text.rfind("}") + 1
        if brace_start >= 0 and brace_end > brace_start:
            json_match = text[brace_start:brace_end]

    if json_match:
        try:
            return json.loads(json_match)
        except json.JSONDecodeError:
            pass

    return {"overall_score": 0.0, "criteria": [], "summary": "Failed to parse grader response"}
