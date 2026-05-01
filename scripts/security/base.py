"""
Security screening base types and protocol.

Defines the provider-agnostic interface that all security providers implement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class ThreatDetail:
    """Individual threat detection detail."""

    detector_type: str
    detected: bool
    message_id: int | None = None
    text: str | None = None
    start: int | None = None
    end: int | None = None
    labels: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialize to dict for evidence JSON."""
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
    """Result of a security screening operation."""

    flagged: bool
    safe_to_proceed: bool
    threats: list[ThreatDetail] = field(default_factory=list)
    request_uuid: str | None = None
    latency_ms: float = 0.0
    provider: str = "noop"
    error: str | None = None
    skipped: bool = False

    def to_dict(self) -> dict:
        """Serialize to dict for evidence JSON."""
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
    """Security screening provider interface."""

    def screen(
        self,
        messages: list[dict],
        *,
        metadata: dict | None = None,
    ) -> ScreeningResult:
        """Screen messages for threats."""
        ...

    def is_available(self) -> bool:
        """Check if the provider is operational."""
        ...
