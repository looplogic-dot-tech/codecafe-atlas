from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from .paths import data_dir


HISTORY_FILENAME = "pdf_separator_history.json"
HISTORY_LIMIT = 500


def separator_history_path() -> Path:
    """Return the persistent local history file used by the PDF separator."""
    return data_dir() / HISTORY_FILENAME


def _normalized_entry(entry: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(entry)
    normalized.setdefault("id", str(uuid4()))
    normalized.setdefault(
        "exported_at",
        datetime.now().astimezone().isoformat(timespec="seconds"),
    )
    normalized.setdefault("document_type", "")
    normalized.setdefault("output_zip", "")
    normalized.setdefault("source_files", [])
    normalized.setdefault("source_file_count", len(normalized["source_files"]))
    normalized.setdefault("page_count", 0)
    normalized.setdefault("identified_count", 0)
    normalized.setdefault("provisional_count", 0)
    normalized.setdefault("categories", {})
    normalized.setdefault("report_file", "")
    return normalized


def load_export_history(path: Path | None = None) -> list[dict[str, Any]]:
    """Load valid history records. A damaged file never blocks the separator."""
    target = Path(path) if path is not None else separator_history_path()
    if not target.exists():
        return []

    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return []

    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def _write_history(records: list[dict[str, Any]], target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(
            json.dumps(records, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(target)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def append_export_history(
    entry: dict[str, Any],
    path: Path | None = None,
    limit: int = HISTORY_LIMIT,
) -> dict[str, Any]:
    """Append one export record and retain the most recent entries."""
    target = Path(path) if path is not None else separator_history_path()
    normalized = _normalized_entry(entry)
    records = load_export_history(target)
    records.append(normalized)
    if limit > 0 and len(records) > limit:
        records = records[-limit:]
    _write_history(records, target)
    return normalized


def clear_export_history(path: Path | None = None) -> None:
    target = Path(path) if path is not None else separator_history_path()
    if target.exists():
        target.unlink()
