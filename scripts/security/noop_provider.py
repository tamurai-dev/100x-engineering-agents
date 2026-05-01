"""
No-op security provider.

Used when Lakera Guard is not configured (API key not set) or when
the requests library is not installed. Always returns safe results.
"""

from __future__ import annotations

from scripts.security.base import ScreeningResult


class NoopProvider:
    """No-op provider that always returns safe results."""

    def screen(
        self,
        messages: list[dict],
        *,
        metadata: dict | None = None,
    ) -> ScreeningResult:
        """Return a safe, non-flagged result without any API call."""
        return ScreeningResult(
            flagged=False,
            safe_to_proceed=True,
            provider="noop",
            skipped=True,
        )

    def is_available(self) -> bool:
        """NoopProvider is always available."""
        return True
