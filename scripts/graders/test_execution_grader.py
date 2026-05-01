"""
Test Execution Grader

test-generator エージェント専用。
エージェントが生成したテストコードの実行結果をセッションイベントから判定する。
"""

from __future__ import annotations

import re

_PYTEST_SUMMARY_RE = re.compile(
    r"=+\s*(?:(\d+)\s+passed)?(?:,?\s*(\d+)\s+failed)?(?:,?\s*(\d+)\s+error)?.*=+"
)


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

    # 全テスト実行結果を結合して判定（最終実行を優先）
    all_test_output = "\n".join(r.get("result", "") or "" for r in test_runs)
    final_run = test_runs[-1]
    test_output = final_run.get("result", "") or ""

    tests_passed = _check_test_passed(all_test_output)

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

    # pytest のサマリー行を解析（最も信頼性が高い）
    m = _PYTEST_SUMMARY_RE.search(output)
    # BetaManagedAgentsTextBlock wrapper の中身も検索
    if not m:
        inner = re.search(r"text=['\"](.+)['\"]\)", output, re.DOTALL)
        if inner:
            m = _PYTEST_SUMMARY_RE.search(inner.group(1))
    if m:
        passed_count = int(m.group(1) or 0)
        failed_count = int(m.group(2) or 0)
        error_count = int(m.group(3) or 0)
        return failed_count == 0 and error_count == 0 and passed_count > 0

    # pytest サマリーが見つからない場合のフォールバック
    fail_patterns = [
        r"\d+\s+failed",
        r"FAILED\s+",
        r"= FAILURES =",
        r"= ERRORS =",
        r"Traceback \(most recent call last\)",
        r"exit code: [12]",
    ]
    pass_patterns = [
        r"\d+\s+passed",
        r"exit code: 0",
        r"all tests passed",
        r"tests passed",
    ]

    has_failure = any(re.search(pat, output, re.IGNORECASE) for pat in fail_patterns)
    has_pass = any(re.search(pat, output, re.IGNORECASE) for pat in pass_patterns)

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
