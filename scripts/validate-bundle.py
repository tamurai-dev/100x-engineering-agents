#!/usr/bin/env python3
"""Actor-Critic Bundle validator (thin shim).

Delegates to :mod:`duo_agents.validators`.

Usage:
    python scripts/validate-bundle.py                                # 全バンドル
    python scripts/validate-bundle.py agents/bundles/my-bundle       # 個別検証
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src"
if SRC_DIR.exists() and str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from duo_agents.validators import (  # noqa: E402
    _validate_agent_ref,
    find_bundle_dirs,
    load_manifest,
    validate_bundle_dir,
)

# Backwards-compatible aliases for tests/test_validate_bundle.py.
__all__ = [
    "_validate_agent_ref",
    "load_manifest",
    "load_schema",
    "validate_bundle",
]


def load_schema() -> dict:
    """Legacy compatibility shim — pydantic now owns the schema."""
    return {}


def validate_bundle(bundle_dir: Path, schema: dict, manifest: dict) -> list[str]:
    """Legacy signature: ``schema`` is ignored (kept for test compatibility)."""
    return validate_bundle_dir(bundle_dir, manifest)


def main() -> None:
    target = sys.argv[1] if len(sys.argv) > 1 else None

    try:
        bundles = find_bundle_dirs(target)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}")
        sys.exit(1)

    if not bundles:
        print("バンドルが見つかりません。スキップします。")
        return

    manifest = load_manifest()
    total_errors: list[str] = []

    print(f"=== Bundle バリデーション（{len(bundles)} バンドル） ===\n")
    for bundle_dir in bundles:
        errors = validate_bundle_dir(bundle_dir, manifest)
        if errors:
            for e in errors:
                print(f"  FAIL: {e}")
            total_errors.extend(errors)
        else:
            print(f"  PASS: {bundle_dir.name}")

    print()
    if total_errors:
        print(f"結果: {len(bundles)} バンドル中 {len(total_errors)} 件のエラー")
        sys.exit(1)
    print(f"結果: {len(bundles)} バンドル — ALL PASSED")


if __name__ == "__main__":
    main()
