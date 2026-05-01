"""データパイプラインモジュール"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


def extract(
    source: str | Path,
    format: str = "csv",
    encoding: str = "utf-8",
    skip_header: bool = True,
    max_rows: int | None = None,
) -> list[dict[str, Any]]:
    source = Path(source)
    if not source.exists():
        raise FileNotFoundError(f"Source file not found: {source}")

    if format == "csv":
        with open(source, encoding=encoding, newline="") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
    elif format == "json":
        with open(source, encoding=encoding) as f:
            rows = json.load(f)
    elif format == "jsonl":
        rows = []
        with open(source, encoding=encoding) as f:
            for line in f:
                if line.strip():
                    rows.append(json.loads(line))
    else:
        raise ValueError(f"Unsupported format: {format}")

    if max_rows is not None:
        rows = rows[:max_rows]

    return rows


def transform(
    records: list[dict[str, Any]],
    rename: dict[str, str] | None = None,
    drop_columns: list[str] | None = None,
    filter_fn: callable | None = None,
    add_columns: dict[str, callable] | None = None,
) -> list[dict[str, Any]]:
    result = []
    for record in records:
        row = dict(record)

        if drop_columns:
            for col in drop_columns:
                row.pop(col, None)

        if rename:
            for old_key, new_key in rename.items():
                if old_key in row:
                    row[new_key] = row.pop(old_key)

        if add_columns:
            for col_name, fn in add_columns.items():
                row[col_name] = fn(row)

        if filter_fn is not None:
            if not filter_fn(row):
                continue

        result.append(row)

    return result


def load(
    records: list[dict[str, Any]],
    destination: str | Path,
    format: str = "csv",
    encoding: str = "utf-8",
    overwrite: bool = False,
) -> int:
    destination = Path(destination)

    if destination.exists() and not overwrite:
        raise FileExistsError(f"Destination already exists: {destination}. Use overwrite=True.")

    destination.parent.mkdir(parents=True, exist_ok=True)

    if format == "csv":
        if not records:
            destination.write_text("", encoding=encoding)
            return 0
        with open(destination, "w", encoding=encoding, newline="") as f:
            writer = csv.DictWriter(f, fieldnames=records[0].keys())
            writer.writeheader()
            writer.writerows(records)
    elif format == "json":
        with open(destination, "w", encoding=encoding) as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
    elif format == "jsonl":
        with open(destination, "w", encoding=encoding) as f:
            for record in records:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
    else:
        raise ValueError(f"Unsupported format: {format}")

    return len(records)
