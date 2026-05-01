"""
Security screening module for 100x-engineering-agents.

Provides transparent security screening for agent inputs and outputs
using Lakera Guard. Falls back to a no-op provider when Lakera is
not configured.

Usage:
    from scripts.security import get_guard, screen_text

    # Get the singleton guard instance
    guard = get_guard()
    result = guard.screen([{"role": "user", "content": "test input"}])

    # Or use the convenience function
    result = screen_text("test input", direction="input")

Environment:
    LAKERA_GUARD_API_KEY  — Set to enable Lakera Guard (unset = disabled)
"""

from __future__ import annotations

import sys
from typing import Union

from scripts.security.base import ScreeningResult, SecurityProvider, ThreatDetail
from scripts.security.config import SecurityConfig
from scripts.security.noop_provider import NoopProvider

__all__ = [
    "get_guard",
    "screen_text",
    "ScreeningResult",
    "SecurityProvider",
    "ThreatDetail",
    "SecurityConfig",
]

_guard_instance: Union[SecurityProvider, None] = None
_logged_messages: set[str] = set()


def _log(level: str, message: str, *, config: SecurityConfig | None = None) -> None:
    """Log a security message to stderr."""
    log_level = (config.log_level if config else "info").lower()
    if log_level == "quiet":
        return
    if log_level == "info" and level == "DEBUG":
        return
    print(f"[security:{level}] {message}", file=sys.stderr)


def _log_once(message: str, *, config: SecurityConfig | None = None) -> None:
    """Log a message only once per session."""
    if message not in _logged_messages:
        _logged_messages.add(message)
        _log("INFO", message, config=config)


def get_guard(*, _force_reload: bool = False) -> SecurityProvider:
    """Get or create the singleton SecurityProvider.

    Returns LakeraGuardProvider if configured, NoopProvider otherwise.
    """
    global _guard_instance
    if _guard_instance is not None and not _force_reload:
        return _guard_instance

    config = SecurityConfig.load()

    if config.is_enabled():
        try:
            import requests  # noqa: F401

            from scripts.security.lakera_provider import LakeraGuardProvider

            _guard_instance = LakeraGuardProvider(config)
            _log_once(
                f"Lakera Guard 有効 (region={config.region}, mode={config.mode})",
                config=config,
            )
        except ImportError:
            _log_once(
                "requests ライブラリが未インストールです。"
                "pip install requests で追加してください。"
                "セキュリティスクリーニングは無効です。",
                config=config,
            )
            _guard_instance = NoopProvider()
    else:
        if config.enabled == "auto" and not config.api_key:
            _log_once(
                "LAKERA_GUARD_API_KEY が未設定のため"
                "セキュリティスクリーニングは無効です。",
                config=config,
            )
        _guard_instance = NoopProvider()

    return _guard_instance


def screen_text(
    text: str,
    *,
    direction: str = "input",
    role: str | None = None,
    context: str | None = None,
    metadata: dict | None = None,
) -> ScreeningResult:
    """Screen a single text string for threats.

    Args:
        text: The text to screen.
        direction: "input" (user content) or "output" (assistant content).
        role: Override the message role (default: "user" for input, "assistant" for output).
        context: Optional system prompt context to include.
        metadata: Optional metadata (session_id, user_id, etc.).

    Returns:
        ScreeningResult with flagged status and threat details.
    """
    guard = get_guard()
    msg_role = role or ("user" if direction == "input" else "assistant")
    messages: list[dict] = [{"role": msg_role, "content": text}]
    if context:
        messages.insert(0, {"role": "system", "content": context})
    return guard.screen(messages, metadata=metadata)
