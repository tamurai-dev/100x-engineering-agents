"""
Code-Based Grader

Ground Truth マッチングと Transcript 分析を行う決定論的 grader。
安価・高速・再現性100%。
"""

from __future__ import annotations

import json
import re
from pathlib import Path


def grade_ground_truth(
    agent_output: str,
    ground_truth_path: Path,
    line_tolerance: int = 5,
) -> dict:
    """
    エージェント出力を ground-truth.json と照合し、Precision / Recall / F1 を計算する。

    Returns:
        {
            "precision": float,
            "recall": float,
            "f1": float,
            "must_find_recall": float,
            "should_find_recall": float,
            "matched": [...],
            "missed": [...],
            "extra": [...]
        }
    """
    with open(ground_truth_path, encoding="utf-8") as f:
        gt = json.load(f)

    issues = gt["issues"]
    output_lower = agent_output.lower()

    matched = []
    missed = []

    for issue in issues:
        found = _match_issue(issue, output_lower, line_tolerance)
        if found:
            matched.append({**issue, "match_evidence": found})
        else:
            missed.append(issue)

    must_find = [i for i in issues if i.get("category") == "must_find"]
    should_find = [i for i in issues if i.get("category") == "should_find"]
    must_find_matched = [i for i in matched if i.get("category") == "must_find"]
    should_find_matched = [i for i in matched if i.get("category") == "should_find"]

    total_found = len(matched)
    total_issues = len(issues)

    precision = 1.0 if total_found == 0 else total_found / max(total_found, 1)
    recall = total_found / total_issues if total_issues > 0 else 1.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

    must_find_recall = (
        len(must_find_matched) / len(must_find) if must_find else 1.0
    )
    should_find_recall = (
        len(should_find_matched) / len(should_find) if should_find else 1.0
    )

    return {
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1": round(f1, 3),
        "must_find_recall": round(must_find_recall, 3),
        "should_find_recall": round(should_find_recall, 3),
        "matched": [_safe_issue(i) for i in matched],
        "missed": [_safe_issue(i) for i in missed],
        "total_issues": total_issues,
        "total_matched": total_found,
    }


def _match_issue(issue: dict, output_lower: str, line_tolerance: int) -> str | None:
    """issue が agent 出力で言及されているか判定する。"""
    file_name = issue["file"]
    issue_type = issue["type"]

    type_keywords = _get_type_keywords(issue_type)

    file_mentioned = file_name.lower() in output_lower

    type_mentioned = any(kw in output_lower for kw in type_keywords)

    if file_mentioned and type_mentioned:
        return f"file={file_name}, type_keyword matched"

    if type_mentioned:
        line_range = issue.get("line_range", [])
        if line_range:
            for line_num in range(
                max(1, line_range[0] - line_tolerance),
                line_range[-1] + line_tolerance + 1,
            ):
                if f":{line_num}" in output_lower or f"行{line_num}" in output_lower:
                    return f"type_keyword + line={line_num}"

    if file_mentioned and issue.get("description"):
        desc_keywords = _extract_keywords(issue["description"])
        desc_hits = sum(1 for kw in desc_keywords if kw.lower() in output_lower)
        if desc_keywords and desc_hits >= max(1, len(desc_keywords) // 2):
            return f"file={file_name}, description_keyword matched ({desc_hits}/{len(desc_keywords)})"

    return None


def _get_type_keywords(issue_type: str) -> list[str]:
    """issue type に対応するキーワード群を返す。"""
    keyword_map = {
        "sql-injection": ["sql injection", "sqlインジェクション", "sql インジェクション", "パラメータ化", "プレースホルダ", "f-string", "f\"select"],
        "command-injection": ["command injection", "コマンドインジェクション", "os.system", "subprocess", "shell=true", "shell injection"],
        "path-traversal": ["path traversal", "パストラバーサル", "ディレクトリトラバーサル", "directory traversal", "../"],
        "hardcoded-secret": ["hardcod", "ハードコード", "secret", "シークレット", "平文", "直接記述", "埋め込"],
        "bare-except": ["bare except", "except:", "例外を握り潰", "例外の握り潰し", "broad exception", "例外処理"],
        "debug-mode": ["debug", "デバッグ", "debug=true", "本番環境"],
        "unrestricted-hosts": ["allowed_hosts", "ワイルドカード", "'*'", "unrestricted"],
        "xss": ["xss", "cross-site scripting", "クロスサイトスクリプティング", "innerhtml", "エスケープ"],
        "csrf": ["csrf", "cross-site request forgery"],
        "ssrf": ["ssrf", "server-side request forgery", "url fetch", "外部url"],
        "missing-auth": ["認証", "authentication", "auth", "ミドルウェア", "middleware", "未認証"],
        "timing-attack": ["timing", "タイミング", "定数時間", "constant-time"],
        "rate-limiting": ["rate limit", "レート制限", "ブルートフォース", "試行回数"],
        "sensitive-log": ["ログ", "log", "センシティブ", "sensitive", "機密情報"],
        "cors-misconfiguration": ["cors", "origin", "access-control"],
        "no-token-expiry": ["expire", "expir", "有効期限", "トークンの期限"],
        "any-type": ["any型", "any 型", ": any", "型安全", "型の安全"],
        "var-usage": ["var ", "var　", "let ", "const ", "var の使用"],
        "loose-equality": ["==", "===", "厳密等価", "strict equal", "loose equal"],
        "unused-variable": ["未使用", "unused", "使われていない"],
        "missing-error-handling": ["エラーハンドリング", "error handling", "try-catch", "例外処理"],
        "unhandled-promise": ["await", "promise", "非同期", "async"],
        "stack-trace-exposure": ["stack", "スタックトレース", "err.stack", "内部情報"],
        "password-leak": ["パスワード", "password", "レスポンス", "response", "漏洩"],
    }
    return keyword_map.get(issue_type, [issue_type.replace("-", " ")])


def _extract_keywords(text: str) -> list[str]:
    """日本語テキストからキーワードを抽出する。"""
    particles = ["の", "が", "を", "に", "で", "は", "と", "も", "から", "まで", "より"]
    keywords = [text]
    for p in particles:
        new_kw = []
        for kw in keywords:
            new_kw.extend(kw.split(p))
        keywords = new_kw
    return [kw.strip() for kw in keywords if len(kw.strip()) >= 2]


def _safe_issue(issue: dict) -> dict:
    """evidence 保存用にシリアライズ安全な issue を返す。"""
    return {k: v for k, v in issue.items() if k != "match_evidence"}


def grade_transcript(events: list[dict]) -> dict:
    """
    セッションイベントから効率性指標を計算する。

    Returns:
        {
            "turns": int,
            "tool_calls": int,
            "tokens_total": int,
            "tokens_input": int,
            "tokens_output": int,
            "duration_seconds": float,
            "tools_used": [str],
            "efficiency_score": float
        }
    """
    turns = 0
    tool_calls = 0
    tokens_input = 0
    tokens_output = 0
    tools_used = []
    timestamps = []

    for event in events:
        event_type = event.get("type", "")

        if event_type == "span.model_request_start":
            turns += 1

        if event_type in ("agent.tool_use", "agent.custom_tool_use", "agent.mcp_tool_use"):
            tool_calls += 1
            tool_name = event.get("tool_name", event.get("name", "unknown"))
            if tool_name not in tools_used:
                tools_used.append(tool_name)

        if event_type == "span.model_request_end":
            usage = event.get("model_usage", {})
            tokens_input += usage.get("input_tokens", 0)
            tokens_output += usage.get("output_tokens", 0)

        processed_at = event.get("processed_at")
        if processed_at:
            timestamps.append(processed_at)

    duration = 0.0
    if len(timestamps) >= 2:
        try:
            from datetime import datetime, timezone

            first = datetime.fromisoformat(timestamps[0].replace("Z", "+00:00"))
            last = datetime.fromisoformat(timestamps[-1].replace("Z", "+00:00"))
            duration = (last - first).total_seconds()
        except (ValueError, TypeError):
            pass

    tokens_total = tokens_input + tokens_output

    turn_score = _threshold_score(turns, excellent=2, acceptable=5)
    tool_score = _threshold_score(tool_calls, excellent=5, acceptable=15)
    token_score = _threshold_score(tokens_total, excellent=3000, acceptable=10000)

    efficiency_score = round((turn_score + tool_score + token_score) / 3, 3)

    return {
        "turns": turns,
        "tool_calls": tool_calls,
        "tokens_total": tokens_total,
        "tokens_input": tokens_input,
        "tokens_output": tokens_output,
        "duration_seconds": round(duration, 1),
        "tools_used": tools_used,
        "efficiency_score": efficiency_score,
        "thresholds": {
            "turns": {"excellent": 2, "acceptable": 5, "actual": turns, "score": turn_score},
            "tool_calls": {"excellent": 5, "acceptable": 15, "actual": tool_calls, "score": tool_score},
            "tokens": {"excellent": 3000, "acceptable": 10000, "actual": tokens_total, "score": token_score},
        },
    }


def _threshold_score(value: int | float, excellent: int | float, acceptable: int | float) -> float:
    """
    しきい値ベースのスコアリング。
    excellent 以下 → 1.0、acceptable 以下 → 線形減衰、それ以上 → 0.0
    """
    if value <= excellent:
        return 1.0
    if value <= acceptable:
        return round(1.0 - (value - excellent) / (acceptable - excellent), 3)
    return 0.0


def grade_output_format(agent_output: str, expected_format: dict) -> dict:
    """
    エージェント出力のフォーマット準拠を検証する。

    expected_format 例:
    {
        "patterns": ["\\[MUST FIX\\|SHOULD FIX\\|CONSIDER\\]"],
        "required_sections": ["ファイルパス", "問題の説明", "推奨される修正方法"]
    }
    """
    patterns = expected_format.get("patterns", [])
    required = expected_format.get("required_sections", [])

    pattern_results = {}
    for pat in patterns:
        try:
            found = bool(re.search(pat, agent_output, re.IGNORECASE))
        except re.error:
            found = pat.lower() in agent_output.lower()
        pattern_results[pat] = found

    section_results = {}
    for section in required:
        section_results[section] = section.lower() in agent_output.lower() or section in agent_output

    pattern_score = sum(pattern_results.values()) / len(pattern_results) if pattern_results else 1.0
    section_score = sum(section_results.values()) / len(section_results) if section_results else 1.0

    return {
        "format_compliance": round((pattern_score + section_score) / 2, 3),
        "pattern_results": pattern_results,
        "section_results": section_results,
    }
