#!/usr/bin/env python3
"""
Bundle バリデーター

bundle.json を bundle.schema.json で検証し、
参照先エージェントの存在・マニフェスト登録もチェックする。

Usage:
    python scripts/validate-bundle.py                         # 全バンドル検証
    python scripts/validate-bundle.py agents/bundles/my-bundle  # 個別検証
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    import jsonschema
except ImportError:
    print("ERROR: jsonschema が必要です。 pip install jsonschema を実行してください。")
    sys.exit(2)


REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = REPO_ROOT / "agents" / "schemas" / "bundle.schema.json"
BUNDLES_DIR = REPO_ROOT / "agents" / "bundles"
AGENTS_DIR = REPO_ROOT / "agents" / "agents"
MANIFEST_PATH = AGENTS_DIR / ".manifest.json"


def load_schema() -> dict:
    """Bundle スキーマを読み込む。"""
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        return json.load(f)


def load_manifest() -> dict:
    """マニフェストを読み込む。"""
    if MANIFEST_PATH.exists():
        with open(MANIFEST_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {"version": 1, "agents": {}}


def validate_bundle(bundle_dir: Path, schema: dict, manifest: dict) -> list[str]:
    """1バンドルを検証する。エラーメッセージのリストを返す。"""
    errors: list[str] = []
    bundle_name = bundle_dir.name

    # bundle.json の存在チェック
    bundle_json_path = bundle_dir / "bundle.json"
    if not bundle_json_path.exists():
        errors.append(f"{bundle_name}: bundle.json が見つかりません")
        return errors

    # JSON パース
    try:
        with open(bundle_json_path, encoding="utf-8") as f:
            bundle = json.load(f)
    except json.JSONDecodeError as e:
        errors.append(f"{bundle_name}: bundle.json の JSON パースエラー: {e}")
        return errors

    # JSON Schema バリデーション
    try:
        jsonschema.validate(bundle, schema)
    except jsonschema.ValidationError as e:
        errors.append(f"{bundle_name}: スキーマ検証エラー: {e.message}")
        return errors

    # バンドル名の整合性チェック
    if bundle.get("name") != bundle_name:
        errors.append(
            f"{bundle_name}: bundle.json の name ({bundle.get('name')}) が "
            f"ディレクトリ名 ({bundle_name}) と一致しません"
        )

    # Task Agent の参照チェック
    task_agent_name = bundle["task_agent"]["name"]
    task_agent_ref = bundle["task_agent"]["ref"]
    task_agent_dir = REPO_ROOT / task_agent_ref

    if not task_agent_dir.exists():
        errors.append(
            f"{bundle_name}: Task Agent ディレクトリが存在しません: {task_agent_ref}"
        )
    elif not (task_agent_dir / "agent.md").exists():
        errors.append(
            f"{bundle_name}: Task Agent の agent.md が見つかりません: {task_agent_ref}/agent.md"
        )

    if task_agent_name not in manifest.get("agents", {}):
        errors.append(
            f"{bundle_name}: Task Agent ({task_agent_name}) がマニフェストに未登録です"
        )

    # QA Agent の参照チェック
    qa_agent_name = bundle["qa_agent"]["name"]
    qa_agent_ref = bundle["qa_agent"]["ref"]
    qa_agent_dir = REPO_ROOT / qa_agent_ref

    if not qa_agent_dir.exists():
        errors.append(
            f"{bundle_name}: QA Agent ディレクトリが存在しません: {qa_agent_ref}"
        )
    elif not (qa_agent_dir / "agent.md").exists():
        errors.append(
            f"{bundle_name}: QA Agent の agent.md が見つかりません: {qa_agent_ref}/agent.md"
        )

    if qa_agent_name not in manifest.get("agents", {}):
        errors.append(
            f"{bundle_name}: QA Agent ({qa_agent_name}) がマニフェストに未登録です"
        )

    # Task Agent と QA Agent が同一でないかチェック
    if task_agent_name == qa_agent_name:
        errors.append(
            f"{bundle_name}: Task Agent と QA Agent が同一です ({task_agent_name})。"
            "Actor-Critic パターンでは別エージェントである必要があります"
        )

    # SKILL ファイルの存在チェック（指定されている場合）
    skill_path = bundle.get("skill")
    if skill_path:
        full_skill_path = REPO_ROOT / skill_path
        if not full_skill_path.exists():
            errors.append(
                f"{bundle_name}: SKILL ファイルが見つかりません: {skill_path}"
            )

    return errors


def find_bundles(target: str | None = None) -> list[Path]:
    """検証対象のバンドルディレクトリを取得する。"""
    if target:
        target_path = Path(target)
        if not target_path.is_absolute():
            target_path = REPO_ROOT / target_path
        if target_path.is_dir():
            return [target_path]
        print(f"ERROR: ディレクトリが見つかりません: {target}")
        sys.exit(1)

    if not BUNDLES_DIR.exists():
        return []

    bundles = []
    for d in sorted(BUNDLES_DIR.iterdir()):
        if d.is_dir() and not d.name.startswith("."):
            bundles.append(d)
    return bundles


def main() -> None:
    target = sys.argv[1] if len(sys.argv) > 1 else None

    schema = load_schema()
    manifest = load_manifest()
    bundles = find_bundles(target)

    if not bundles:
        print("バンドルが見つかりません。スキップします。")
        return

    total_errors: list[str] = []
    validated = 0

    print(f"=== Bundle バリデーション（{len(bundles)} バンドル） ===")
    print()

    for bundle_dir in bundles:
        errors = validate_bundle(bundle_dir, schema, manifest)
        if errors:
            for e in errors:
                print(f"  FAIL: {e}")
            total_errors.extend(errors)
        else:
            print(f"  PASS: {bundle_dir.name}")
        validated += 1

    print()
    if total_errors:
        print(f"結果: {validated} バンドル中 {len(total_errors)} 件のエラー")
        sys.exit(1)
    else:
        print(f"結果: {validated} バンドル — ALL PASSED")


if __name__ == "__main__":
    main()
