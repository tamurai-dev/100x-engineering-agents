#!/usr/bin/env python3
"""Actor-Critic Duet validator (thin shim).

Delegates to :mod:`duo_agents.validators`.

Usage:
    python scripts/validate-duet.py                                # 全デュエット
    python scripts/validate-duet.py agents/duets/my-duet       # 個別検証
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
    find_duet_dirs,
    load_manifest,
    validate_duet_dir,
)

# Backwards-compatible aliases for tests/test_validate_duet.py.
__all__ = [
    "_validate_agent_ref",
    "load_manifest",
    "load_schema",
    "validate_duet",
]


def load_schema() -> dict:
    """Legacy compatibility shim — pydantic now owns the schema."""
    return {}


def validate_duet(duet_dir: Path, schema: dict, manifest: dict) -> list[str]:
    """Legacy signature: ``schema`` is ignored (kept for test compatibility)."""
    return validate_duet_dir(duet_dir, manifest)


def main() -> None:
    target = sys.argv[1] if len(sys.argv) > 1 else None

    try:
        duets = find_duet_dirs(target)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}")
        sys.exit(1)

    if not duets:
        print("デュエットが見つかりません。スキップします。")
        return

    manifest = load_manifest()
    total_errors: list[str] = []

    print(f"=== Duet バリデーション（{len(duets)} デュエット） ===\n")
    for duet_dir in duets:
        errors = validate_duet_dir(duet_dir, manifest)
        if errors:
            for e in errors:
                print(f"  FAIL: {e}")
            total_errors.extend(errors)
        else:
            print(f"  PASS: {duet_dir.name}")

    print()
    if total_errors:
        print(f"結果: {len(duets)} デュエット中 {len(total_errors)} 件のエラー")
        sys.exit(1)
    print(f"結果: {len(duets)} デュエット — ALL PASSED")


if __name__ == "__main__":
    main()
