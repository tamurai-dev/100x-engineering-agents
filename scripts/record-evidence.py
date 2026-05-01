#!/usr/bin/env python3
"""
Execution Evidence Recorder — 動作検証証跡の記録ツール

成果物（スクリプト・エージェント）の動作検証結果を構造化 JSON として記録する。
JSON Schema で形式を強制し、HMAC-SHA256 で改竄を検出する。

サブコマンド:
    run     コマンドを実行し、出力を自動キャプチャして証跡に記録
    log     手動の検証結果（セッション証跡）を記録
    summary evidence/SUMMARY.md を再生成
    verify  全証跡エントリの HMAC 署名を検証

Usage:
    # スクリプト証跡（自動キャプチャ）
    python scripts/record-evidence.py run \\
        --subject scripts/create-subagent.sh \\
        --type new-script \\
        --name "正常系: 新規エージェント作成" \\
        -- make create-agent NAME=test-agent

    # セッション証跡（手動記録）
    python scripts/record-evidence.py log \\
        --subject agents/agents/code-reviewer.md \\
        --type new-agent \\
        --name "Claude Code セッションでの動作確認" \\
        --result pass \\
        --note "PRレビュー依頼に対して自動起動を確認"

    # SUMMARY.md を再生成
    python scripts/record-evidence.py summary

    # 全証跡の署名検証
    python scripts/record-evidence.py verify
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import hmac
import json
import os
import re
import subprocess
import sys
from pathlib import Path

try:
    import jsonschema
except ImportError:
    print("ERROR: jsonschema が必要です。 pip install jsonschema を実行してください。")
    sys.exit(2)


REPO_ROOT = Path(__file__).resolve().parent.parent
EVIDENCE_DIR = REPO_ROOT / "evidence"
ENTRIES_DIR = EVIDENCE_DIR / "entries"
SCHEMA_PATH = EVIDENCE_DIR / "schema" / "evidence.schema.json"
SUMMARY_PATH = EVIDENCE_DIR / "SUMMARY.md"
KEY_PATH = REPO_ROOT / ".manifest-key"


# ── 鍵管理 ─────────────────────────────────────────

def get_key() -> bytes:
    env_key = os.environ.get("MANIFEST_HMAC_KEY")
    if env_key:
        return env_key.encode("utf-8")
    if KEY_PATH.exists():
        return KEY_PATH.read_bytes().strip()
    key = os.urandom(32).hex().encode("utf-8")
    KEY_PATH.write_bytes(key)
    return key


def compute_evidence_hmac(key: bytes, entry: dict) -> str:
    payload = json.dumps(
        {k: v for k, v in entry.items() if k != "hmac_sha256"},
        sort_keys=True, ensure_ascii=False
    ).encode("utf-8")
    return hmac.new(key, payload, hashlib.sha256).hexdigest()


# ── スキーマ ────────────────────────────────────────

def load_schema() -> dict:
    with open(SCHEMA_PATH) as f:
        return json.load(f)


def validate_entry(entry: dict, schema: dict) -> list[str]:
    validator = jsonschema.Draft202012Validator(schema)
    errors = []
    for error in sorted(validator.iter_errors(entry), key=lambda e: list(e.path)):
        path = ".".join(str(p) for p in error.absolute_path) or "(root)"
        errors.append(f"  [{path}] {error.message}")
    return errors


# ── git ─────────────────────────────────────────────

def get_current_commit() -> str:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, cwd=str(REPO_ROOT)
        )
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


# ── エントリ保存 ────────────────────────────────────

def make_entry_filename(subject: str) -> str:
    date_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    safe_name = re.sub(r"[^a-zA-Z0-9_-]", "-", subject.replace("/", "_"))
    safe_name = re.sub(r"-+", "-", safe_name).strip("-")
    return f"{date_str}_{safe_name}.json"


def save_entry(entry: dict) -> Path:
    ENTRIES_DIR.mkdir(parents=True, exist_ok=True)
    filename = make_entry_filename(entry["subject"])
    filepath = ENTRIES_DIR / filename

    # Same subject on same day → append verifications
    if filepath.exists():
        with open(filepath) as f:
            existing = json.load(f)
        existing["verifications"].extend(entry["verifications"])
        existing["hmac_sha256"] = compute_evidence_hmac(get_key(), existing)
        entry = existing

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(entry, f, ensure_ascii=False, indent=2)
        f.write("\n")

    return filepath


# ── run サブコマンド ────────────────────────────────

def cmd_run(args: argparse.Namespace, extra_args: list[str]) -> int:
    if not extra_args:
        print("ERROR: 実行するコマンドを -- の後に指定してください")
        return 1

    command_str = " ".join(extra_args)
    print(f"[evidence:run] 実行: {command_str}")
    print()

    result = subprocess.run(
        extra_args,
        capture_output=True, text=True,
        cwd=str(REPO_ROOT),
        timeout=300
    )

    stdout_snippet = result.stdout[:2000] if result.stdout else ""
    stderr_snippet = result.stderr[:1000] if result.stderr else ""

    # Show output
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)

    verification = {
        "name": args.name,
        "command": command_str,
        "exit_code": result.returncode,
        "stdout_snippet": stdout_snippet,
        "result": "pass" if result.returncode == 0 else "fail",
    }
    if stderr_snippet:
        verification["stderr_snippet"] = stderr_snippet

    key = get_key()
    entry = {
        "subject": args.subject,
        "type": args.type,
        "date": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "commit": get_current_commit(),
        "verifications": [verification],
        "hmac_sha256": "",
    }
    entry["hmac_sha256"] = compute_evidence_hmac(key, entry)

    schema = load_schema()
    errors = validate_entry(entry, schema)
    if errors:
        print("\n[evidence:run] WARNING: スキーマ検証エラー:")
        for e in errors:
            print(e)

    filepath = save_entry(entry)
    print(f"\n[evidence:run] 証跡を記録: {filepath.relative_to(REPO_ROOT)}")
    print(f"  result: {verification['result']}")

    return result.returncode


# ── log サブコマンド ────────────────────────────────

def cmd_log(args: argparse.Namespace) -> int:
    verification = {
        "name": args.name,
        "result": args.result,
    }
    if args.note:
        verification["note"] = args.note
    if args.command:
        verification["command"] = args.command

    key = get_key()
    entry = {
        "subject": args.subject,
        "type": args.type,
        "date": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "commit": get_current_commit(),
        "verifications": [verification],
        "hmac_sha256": "",
    }
    entry["hmac_sha256"] = compute_evidence_hmac(key, entry)

    schema = load_schema()
    errors = validate_entry(entry, schema)
    if errors:
        print("[evidence:log] ERROR: スキーマ検証エラー:")
        for e in errors:
            print(e)
        return 1

    filepath = save_entry(entry)
    print(f"[evidence:log] 証跡を記録: {filepath.relative_to(REPO_ROOT)}")
    print(f"  subject: {args.subject}")
    print(f"  result:  {args.result}")

    return 0


# ── summary サブコマンド ────────────────────────────

def cmd_summary() -> int:
    entries = sorted(ENTRIES_DIR.glob("*.json")) if ENTRIES_DIR.exists() else []

    lines = [
        "<!-- このファイルは自動生成です。手動で編集しないでください。 -->",
        "<!-- python scripts/record-evidence.py summary で再生成できます。 -->",
        "",
        "# Evidence Summary — 動作検証証跡一覧",
        "",
        f"最終更新: {datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"証跡数: {len(entries)}",
        "",
        "| 日付 | 対象 | 種別 | 検証数 | 結果 |",
        "|------|------|------|--------|------|",
    ]

    for entry_path in entries:
        try:
            with open(entry_path) as f:
                entry = json.load(f)
            date = entry.get("date", "")[:10]
            subject = entry.get("subject", "")
            etype = entry.get("type", "")
            verifications = entry.get("verifications", [])
            n_pass = sum(1 for v in verifications if v.get("result") == "pass")
            n_fail = sum(1 for v in verifications if v.get("result") == "fail")
            n_total = len(verifications)

            if n_fail > 0:
                status = f"{n_pass}/{n_total} PASS, **{n_fail} FAIL**"
            else:
                status = f"{n_pass}/{n_total} PASS"

            lines.append(f"| {date} | `{subject}` | {etype} | {n_total} | {status} |")
        except Exception as e:
            lines.append(f"| ? | `{entry_path.name}` | ERROR | - | {e} |")

    if not entries:
        lines.append("| - | - | - | - | 証跡なし |")

    lines.append("")
    SUMMARY_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"[evidence:summary] 生成: {SUMMARY_PATH.relative_to(REPO_ROOT)}")
    return 0


# ── verify サブコマンド ─────────────────────────────

def cmd_verify() -> int:
    entries = sorted(ENTRIES_DIR.glob("*.json")) if ENTRIES_DIR.exists() else []
    if not entries:
        print("証跡エントリがありません。")
        return 0

    key = get_key()
    schema = load_schema()
    passed = 0
    failed = 0

    for entry_path in entries:
        try:
            with open(entry_path) as f:
                entry = json.load(f)
        except Exception as e:
            print(f"  FAIL: {entry_path.name} — JSON パースエラー: {e}")
            failed += 1
            continue

        # Schema validation
        errors = validate_entry(entry, schema)
        if errors:
            print(f"  FAIL: {entry_path.name} — スキーマ検証エラー")
            for e in errors:
                print(e)
            failed += 1
            continue

        # HMAC verification
        expected = compute_evidence_hmac(key, entry)
        stored = entry.get("hmac_sha256", "")
        if not hmac.compare_digest(stored, expected):
            print(f"  FAIL: {entry_path.name} — HMAC 署名不正")
            failed += 1
            continue

        passed += 1

    print(f"\n証跡検証: {passed} passed / {failed} failed / {len(entries)} total")
    return 1 if failed > 0 else 0


# ── メイン ──────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Execution Evidence Recorder")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # run
    p_run = subparsers.add_parser("run", help="コマンドを実行し証跡を自動記録")
    p_run.set_defaults(command="run")
    p_run.add_argument("--subject", required=True, help="検証対象ファイルパス")
    p_run.add_argument("--type", required=True, choices=["new-script", "modified-script", "new-agent", "modified-agent", "integration", "other"])
    p_run.add_argument("--name", required=True, help="検証項目名")

    # log
    p_log = subparsers.add_parser("log", help="手動で検証結果を記録")
    p_log.set_defaults(command="log")
    p_log.add_argument("--subject", required=True, help="検証対象ファイルパス")
    p_log.add_argument("--type", required=True, choices=["new-script", "modified-script", "new-agent", "modified-agent", "integration", "other"])
    p_log.add_argument("--name", required=True, help="検証項目名")
    p_log.add_argument("--result", required=True, choices=["pass", "fail", "skip"])
    p_log.add_argument("--note", help="補足説明")
    p_log.add_argument("--command", help="実行したコマンド（参考情報）")

    # summary
    p_summary = subparsers.add_parser("summary", help="SUMMARY.md を再生成")
    p_summary.set_defaults(command="summary")

    # verify
    p_verify = subparsers.add_parser("verify", help="全証跡の HMAC 署名を検証")
    p_verify.set_defaults(command="verify")

    # Parse (handle -- separator for run command)
    argv = sys.argv[1:]
    extra_args = []
    if len(argv) > 0 and argv[0] == "run" and "--" in argv:
        dash_idx = argv.index("--")
        extra_args = argv[dash_idx + 1:]
        argv = argv[:dash_idx]

    args = parser.parse_args(argv)

    if args.command == "run":
        sys.exit(cmd_run(args, extra_args))
    elif args.command == "log":
        sys.exit(cmd_log(args))
    elif args.command == "summary":
        sys.exit(cmd_summary())
    elif args.command == "verify":
        sys.exit(cmd_verify())


if __name__ == "__main__":
    main()
