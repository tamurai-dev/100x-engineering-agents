"""
Test Execution Grader

test-generator エージェント専用。
エージェントが生成したテストコードの実行結果をセッションイベントから判定する。
"""

from __future__ import annotations


def grade_test_execution(events: list[dict]) -> dict:
    """
    セッションイベントからテスト実行結果を判定する。

    test-generator は同一セッション内でテストを実行するため、
    bash ツールの実行結果（exit code, stdout）からテスト結果を取得する。

    Returns:
        {
            "tests_executed": bool,
            "tests_passed": bool,
            "test_output": str,
            "exit_code": int | None,
            "score": float
        }
    """
    test_runs = []
    last_bash_result = None

    for i, event in enumerate(events):
        event_type = event.get("type", "")

        if event_type == "agent.tool_use":
            tool_name = event.get("tool_name", event.get("name", ""))
            if tool_name == "bash":
                input_text = _get_event_input(event)
                if _is_test_command(input_text):
                    test_runs.append({
                        "command": input_text,
                        "index": i,
                        "result": None,
                    })

        if event_type == "agent.tool_result" and test_runs:
            latest_run = test_runs[-1]
            if latest_run["result"] is None:
                content = _get_event_content(event)
                latest_run["result"] = content
                last_bash_result = content

    if not test_runs:
        return {
            "tests_executed": False,
            "tests_passed": False,
            "test_output": "",
            "exit_code": None,
            "score": 0.0,
            "reason": "テスト実行コマンドが見つからなかった",
        }

    final_run = test_runs[-1]
    test_output = final_run.get("result", "") or ""

    tests_passed = _check_test_passed(test_output)

    return {
        "tests_executed": True,
        "tests_passed": tests_passed,
        "test_output": test_output[:2000],
        "total_test_runs": len(test_runs),
        "score": 1.0 if tests_passed else 0.3,
        "reason": "全テスト PASS" if tests_passed else "テスト失敗あり",
    }


def _is_test_command(text: str) -> bool:
    """テスト実行コマンドかどうかを判定する。"""
    if not text:
        return False
    text_lower = text.lower()
    test_patterns = [
        "pytest",
        "python -m pytest",
        "python3 -m pytest",
        "python -c",
        "python3 -c",
        "npm test",
        "npx jest",
        "npx vitest",
        "node --test",
    ]
    return any(pat in text_lower for pat in test_patterns)


def _check_test_passed(output: str) -> bool:
    """テスト出力から成功/失敗を判定する。"""
    if not output:
        return False
    output_lower = output.lower()

    fail_indicators = [
        "failed",
        "failure",
        "error",
        "traceback",
        "assertion error",
        "assertionerror",
        "exit code: 1",
        "exit code: 2",
    ]
    pass_indicators = [
        "passed",
        "ok",
        "exit code: 0",
        "tests passed",
        "all tests passed",
    ]

    has_failure = any(ind in output_lower for ind in fail_indicators)
    has_pass = any(ind in output_lower for ind in pass_indicators)

    if has_pass and not has_failure:
        return True
    if has_failure:
        return False

    return False


def _get_event_input(event: dict) -> str:
    """イベントから入力テキストを取得する。"""
    if "input" in event:
        inp = event["input"]
        if isinstance(inp, str):
            return inp
        if isinstance(inp, dict):
            return inp.get("command", inp.get("text", str(inp)))
    return ""


def _get_event_content(event: dict) -> str:
    """イベントからコンテンツを取得する。"""
    content = event.get("content", event.get("content_preview", ""))
    if isinstance(content, list):
        return "\n".join(str(c) for c in content)
    return str(content)
