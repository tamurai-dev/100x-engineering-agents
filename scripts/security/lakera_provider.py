"""
Lakera Guard API プロバイダー。

Lakera Guard v2 API を使用して SecurityProvider プロトコルを実装する。
API 通信、エラーハンドリング、レスポンス解析をすべて処理する。
"""

from __future__ import annotations

import time

from scripts.security.base import ScreeningResult, ThreatDetail
from scripts.security.config import SecurityConfig

# requests is an optional dependency
try:
    import requests

    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


class LakeraGuardProvider:
    """Lakera Guard API 実装。"""

    REGION_ENDPOINTS = {
        "auto": "https://api.lakera.ai",
        "ap": "https://ap-southeast-1.api.lakera.ai",
        "us-east": "https://us-east-1.api.lakera.ai",
        "us-west": "https://us-west-2.api.lakera.ai",
        "eu": "https://eu-west-1.api.lakera.ai",
    }

    REQUEST_TIMEOUT = 10

    def __init__(self, config: SecurityConfig):
        self._config = config
        self._api_key = config.api_key
        self._base_url = self.REGION_ENDPOINTS.get(
            config.region, self.REGION_ENDPOINTS["auto"]
        )
        self._session: requests.Session | None = None
        self._disabled_reason: str | None = None

    def screen(
        self,
        messages: list[dict],
        *,
        metadata: dict | None = None,
    ) -> ScreeningResult:
        """Lakera Guard API 経由でメッセージをスクリーニングする。"""
        if not HAS_REQUESTS:
            return ScreeningResult(
                flagged=False,
                safe_to_proceed=True,
                error="requests library not installed",
                provider="lakera",
                skipped=True,
            )

        if self._disabled_reason:
            return ScreeningResult(
                flagged=False,
                safe_to_proceed=True,
                error=self._disabled_reason,
                provider="lakera",
                skipped=True,
            )

        body: dict = {"messages": messages}
        if self._config.project_id:
            body["project_id"] = self._config.project_id
        if self._config.breakdown:
            body["breakdown"] = True
            body["payload"] = True
        if metadata:
            body["metadata"] = metadata

        try:
            start = time.monotonic()
            resp = self._get_session().post(
                f"{self._base_url}/v2/guard",
                json=body,
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=self.REQUEST_TIMEOUT,
            )
            latency_ms = (time.monotonic() - start) * 1000

            if resp.status_code == 401:
                self._disabled_reason = (
                    "Lakera Guard API key is invalid (401). "
                    "Security screening disabled for this session."
                )
                return ScreeningResult(
                    flagged=False,
                    safe_to_proceed=True,
                    error=self._disabled_reason,
                    provider="lakera",
                    latency_ms=latency_ms,
                )

            resp.raise_for_status()
            data = resp.json()

        except requests.exceptions.Timeout:
            return ScreeningResult(
                flagged=False,
                safe_to_proceed=True,
                error="Lakera Guard API timeout",
                provider="lakera",
            )
        except requests.exceptions.RequestException as e:
            return ScreeningResult(
                flagged=False,
                safe_to_proceed=True,
                error=f"Lakera Guard API error: {e}",
                provider="lakera",
            )

        threats = self._parse_threats(data)
        flagged = data.get("flagged", False)
        safe_to_proceed = not flagged or self._config.mode != "block"

        return ScreeningResult(
            flagged=flagged,
            safe_to_proceed=safe_to_proceed,
            threats=threats,
            request_uuid=data.get("metadata", {}).get("request_uuid"),
            latency_ms=latency_ms,
            provider="lakera",
        )

    def is_available(self) -> bool:
        """プロバイダーが稼働中かチェックする。"""
        return HAS_REQUESTS and self._disabled_reason is None

    def _get_session(self) -> requests.Session:
        """永続的な HTTP セッションを取得または作成する。"""
        if self._session is None:
            self._session = requests.Session()
        return self._session

    @staticmethod
    def _parse_threats(data: dict) -> list[ThreatDetail]:
        """API レスポンスから脅威詳細を解析する。"""
        threats: list[ThreatDetail] = []

        # Parse breakdown (detector-level results)
        for item in data.get("breakdown", []):
            if item.get("detected"):
                threats.append(
                    ThreatDetail(
                        detector_type=item.get("detector_type", "unknown"),
                        detected=True,
                        message_id=item.get("message_id"),
                    )
                )

        # Parse payload (PII/match locations)
        for item in data.get("payload", []):
            threats.append(
                ThreatDetail(
                    detector_type=item.get("detector_type", "unknown"),
                    detected=True,
                    text=item.get("text"),
                    start=item.get("start"),
                    end=item.get("end"),
                    labels=item.get("labels", []),
                    message_id=item.get("message_id"),
                )
            )

        # If flagged but no breakdown/payload, add generic threat
        if data.get("flagged") and not threats:
            threats.append(ThreatDetail(detector_type="unknown", detected=True))

        return threats
