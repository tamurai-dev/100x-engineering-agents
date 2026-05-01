"""
100x-engineering-agents 用セキュリティスクリーニングモジュール。

Lakera Guard を使用してエージェントの入出力に透過的なセキュリティスクリーニングを提供する。
Lakera が未設定の場合は No-op プロバイダーにフォールバックする。

使用例:
    from scripts.security import get_guard, screen_text

    # シングルトンガードインスタンスを取得
    guard = get_guard()
    result = guard.screen([{"role": "user", "content": "テスト入力"}])

    # または便利関数を使用
    result = screen_text("テスト入力", direction="input")

環境変数:
    LAKERA_GUARD_API_KEY  — 設定すると Lakera Guard が有効になる（未設定 = 無効）
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
    """セキュリティメッセージを stderr にログ出力する。"""
    log_level = (config.log_level if config else "info").lower()
    if log_level == "quiet":
        return
    if log_level == "info" and level == "DEBUG":
        return
    print(f"[security:{level}] {message}", file=sys.stderr)


def _log_once(message: str, *, config: SecurityConfig | None = None) -> None:
    """セッション中に1回だけメッセージをログ出力する。"""
    if message not in _logged_messages:
        _logged_messages.add(message)
        _log("INFO", message, config=config)


def get_guard(*, _force_reload: bool = False) -> SecurityProvider:
    """シングルトン SecurityProvider を取得または作成する。

    設定済みの場合 LakeraGuardProvider、それ以外は NoopProvider を返す。
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
    """単一のテキスト文字列の脅威をスクリーニングする。

    Args:
        text: スクリーニング対象のテキスト。
        direction: "input"（ユーザーコンテンツ）または "output"（アシスタントコンテンツ）。
        role: メッセージロールのオーバーライド（デフォルト: input="user", output="assistant"）。
        context: システムプロンプトのコンテキスト（任意）。
        metadata: メタデータ（session_id, user_id 等）（任意）。

    Returns:
        フラグ状態と脅威詳細を含む ScreeningResult。
    """
    guard = get_guard()
    msg_role = role or ("user" if direction == "input" else "assistant")
    messages: list[dict] = [{"role": msg_role, "content": text}]
    if context:
        messages.insert(0, {"role": "system", "content": context})
    return guard.screen(messages, metadata=metadata)
