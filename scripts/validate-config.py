#!/usr/bin/env python3
"""Managed Agents ``config.json`` validator (thin shim).

Delegates to :mod:`duo_agents.validators`.

Usage:
    python scripts/validate-config.py                                  # 全エージェント
    python scripts/validate-config.py agents/agents/code-reviewer      # 個別検証
    python scripts/validate-config.py --check-consistency              # 整合性のみ
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src"
if SRC_DIR.exists() and str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from duo_agents.validators import (  # noqa: E402
    find_agent_config_dirs,
    validate_agent_config,
)


def main() -> None:
    check_only = "--check-consistency" in sys.argv
    explicit_dirs = [a for a in sys.argv[1:] if not a.startswith("--")]

    agent_dirs = (
        [Path(d) for d in explicit_dirs]
        if explicit_dirs
        else find_agent_config_dirs()
    )

    if not agent_dirs:
        print("検証対象のエージェントが見つかりません")
        sys.exit(1)

    passed = failed = 0
    for agent_dir in agent_dirs:
        agent_dir = Path(agent_dir).resolve()
        success, errors = validate_agent_config(agent_dir, check_consistency_only=check_only)
        if success:
            print(f"  PASS: {agent_dir.name}")
            passed += 1
        else:
            print(f"  FAIL: {agent_dir.name}")
            for err in errors:
                print(err)
            failed += 1

    print(f"\n{'=' * 40}")
    print(f"  {passed} passed / {failed} failed / {passed + failed} total")
    print(f"{'=' * 40}")
    sys.exit(1 if failed > 0 else 0)


if __name__ == "__main__":
    main()
