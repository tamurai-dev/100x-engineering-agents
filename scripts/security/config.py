"""
Security configuration management.

Loads settings from environment variables and optional security.json file.
Priority: environment variables > security.json > defaults.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SECURITY_JSON_PATH = REPO_ROOT / "security.json"

# Default screening configuration
DEFAULT_SCREENING = {
    "test_agent": {"input": True, "output": True},
    "bundle": {"input": True, "output": True, "qa_output": True, "feedback": True},
    "factory": {"spec_input": True, "generated_output": False},
}

DEFAULT_MESSAGES = {
    "threat_detected": "⚠ セキュリティ警告: 入力に潜在的な脅威が検出されました。内容を確認してください。",
    "pii_detected": "⚠ 個人情報の可能性がある内容が検出されました。",
    "blocked": "セキュリティポリシーにより、この操作はブロックされました。",
}


@dataclass
class SecurityConfig:
    """Security layer configuration."""

    api_key: str = ""
    project_id: str = ""
    enabled: str = "auto"
    mode: str = "warn"
    region: str = "auto"
    log_level: str = "info"
    breakdown: bool = False
    screening: dict = field(default_factory=lambda: dict(DEFAULT_SCREENING))
    messages: dict = field(default_factory=lambda: dict(DEFAULT_MESSAGES))

    def is_enabled(self) -> bool:
        """Determine if security screening should be active."""
        if self.enabled == "true":
            return bool(self.api_key)
        if self.enabled == "false":
            return False
        # auto: enabled if API key is set
        return bool(self.api_key)

    def should_screen(self, context: str, phase: str) -> bool:
        """Check if a specific screening point is enabled.

        Args:
            context: "test_agent", "bundle", or "factory"
            phase: e.g., "input", "output", "qa_output", "feedback", "spec_input"
        """
        ctx_config = self.screening.get(context, {})
        return bool(ctx_config.get(phase, True))

    @classmethod
    def load(cls) -> SecurityConfig:
        """Load configuration from environment variables and security.json."""
        file_config = cls._load_json()

        return cls(
            api_key=os.environ.get("LAKERA_GUARD_API_KEY", ""),
            project_id=os.environ.get(
                "LAKERA_GUARD_PROJECT_ID",
                file_config.get("project_id", ""),
            ),
            enabled=os.environ.get(
                "LAKERA_GUARD_ENABLED",
                file_config.get("enabled", "auto"),
            ),
            mode=os.environ.get(
                "LAKERA_GUARD_MODE",
                file_config.get("mode", "warn"),
            ),
            region=os.environ.get(
                "LAKERA_GUARD_REGION",
                file_config.get("region", "auto"),
            ),
            log_level=os.environ.get(
                "LAKERA_GUARD_LOG_LEVEL",
                file_config.get("log_level", "info"),
            ),
            breakdown=os.environ.get(
                "LAKERA_GUARD_BREAKDOWN",
                str(file_config.get("breakdown", False)),
            ).lower() == "true",
            screening=cls._merge_screening(file_config.get("screening", {})),
            messages={**DEFAULT_MESSAGES, **file_config.get("messages", {})},
        )

    @staticmethod
    def _load_json() -> dict:
        """Load security.json if it exists."""
        if SECURITY_JSON_PATH.exists():
            try:
                with open(SECURITY_JSON_PATH, encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    @staticmethod
    def _merge_screening(file_screening: dict) -> dict:
        """Merge file-based screening config with defaults."""
        result = dict(DEFAULT_SCREENING)
        for key, val in file_screening.items():
            if key in result and isinstance(val, dict):
                result[key] = {**result[key], **val}
            else:
                result[key] = val
        return result
