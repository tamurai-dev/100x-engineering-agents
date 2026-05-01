"""
No-op セキュリティプロバイダー。

Lakera Guard が未設定（API キー未設定）または requests ライブラリが未インストールの場合に使用する。
常に安全な結果を返す。
"""

from __future__ import annotations

from scripts.security.base import ScreeningResult


class NoopProvider:
    """常に安全な結果を返す No-op プロバイダー。"""

    def screen(
        self,
        messages: list[dict],
        *,
        metadata: dict | None = None,
    ) -> ScreeningResult:
        """API 呼び出しなしで安全な非フラグ結果を返す。"""
        return ScreeningResult(
            flagged=False,
            safe_to_proceed=True,
            provider="noop",
            skipped=True,
        )

    def is_available(self) -> bool:
        """NoopProvider は常に利用可能。"""
        return True
