"""
セキュリティスクリーニングの基本型とプロトコル。

全セキュリティプロバイダーが実装するプロバイダー非依存のインターフェースを定義する。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class ThreatDetail:
    """個別の脅威検出詳細。"""

    detector_type: str
    detected: bool
    message_id: int | None = None
    text: str | None = None
    start: int | None = None
    end: int | None = None
    labels: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """evidence JSON 用に辞書へシリアライズする。"""
        d: dict = {"detector_type": self.detector_type, "detected": self.detected}
        if self.message_id is not None:
            d["message_id"] = self.message_id
        if self.text is not None:
            d["text"] = self.text
        if self.start is not None:
            d["start"] = self.start
        if self.end is not None:
            d["end"] = self.end
        if self.labels:
            d["labels"] = self.labels
        return d


@dataclass
class ScreeningResult:
    """セキュリティスクリーニング操作の結果。"""

    flagged: bool
    safe_to_proceed: bool
    threats: list[ThreatDetail] = field(default_factory=list)
    request_uuid: str | None = None
    latency_ms: float = 0.0
    provider: str = "noop"
    error: str | None = None
    skipped: bool = False

    def to_dict(self) -> dict:
        """evidence JSON 用に辞書へシリアライズする。"""
        d: dict = {
            "flagged": self.flagged,
            "provider": self.provider,
            "latency_ms": round(self.latency_ms, 1),
        }
        if self.threats:
            d["threats"] = [t.to_dict() for t in self.threats]
        if self.request_uuid:
            d["request_uuid"] = self.request_uuid
        if self.error:
            d["error"] = self.error
        if self.skipped:
            d["skipped"] = True
        return d


class SecurityProvider(Protocol):
    """セキュリティスクリーニングプロバイダーのインターフェース。"""

    def screen(
        self,
        messages: list[dict],
        *,
        metadata: dict | None = None,
    ) -> ScreeningResult:
        """メッセージの脅威をスクリーニングする。"""
        ...

    def is_available(self) -> bool:
        """プロバイダーが稼働中かチェックする。"""
        ...
