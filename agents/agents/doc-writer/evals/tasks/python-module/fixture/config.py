"""パイプライン設定クラス"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class PipelineConfig:
    source_path: str | Path
    destination_path: str | Path
    source_format: str = "csv"
    destination_format: str = "csv"
    encoding: str = "utf-8"
    max_rows: int | None = None
    overwrite: bool = False
    rename_columns: dict[str, str] = field(default_factory=dict)
    drop_columns: list[str] = field(default_factory=list)
    filter_expression: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> list[str]:
        errors = []
        supported_formats = ("csv", "json", "jsonl")
        if self.source_format not in supported_formats:
            errors.append(f"Unsupported source_format: {self.source_format}")
        if self.destination_format not in supported_formats:
            errors.append(f"Unsupported destination_format: {self.destination_format}")
        if not self.source_path:
            errors.append("source_path is required")
        if not self.destination_path:
            errors.append("destination_path is required")
        return errors
