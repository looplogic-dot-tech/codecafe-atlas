from __future__ import annotations

from pathlib import Path


def next_available_path(path: str | Path) -> Path:
    """Return a collision-free path without replacing an existing file.

    The requested name is kept when available. If it already exists, numeric
    suffixes begin at ``_2`` and increase until a free name is found.
    """

    requested = Path(path)
    if not requested.exists():
        return requested

    suffix = requested.suffix
    stem = requested.stem
    sequence = 2

    while True:
        candidate = requested.with_name(f"{stem}_{sequence}{suffix}")
        if not candidate.exists():
            return candidate
        sequence += 1
