from __future__ import annotations

import hashlib
from collections import defaultdict
from pathlib import Path
from typing import Callable, Iterable


class DuplicateScanCancelled(RuntimeError):
    """Raised when the caller cancels a duplicate scan."""


ProgressCallback = Callable[[int, int, Path], None]
CancelCallback = Callable[[], bool]


def path_is_within_root(path: Path, root: Path) -> bool:
    """Return True only when the resolved path is inside the resolved root."""
    try:
        Path(path).resolve().relative_to(Path(root).resolve())
        return True
    except (OSError, ValueError):
        return False


def sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    """Return the SHA-256 digest of *path* without loading it entirely in memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def find_exact_duplicate_groups(
    paths: Iterable[Path],
    *,
    progress: ProgressCallback | None = None,
    should_cancel: CancelCallback | None = None,
) -> tuple[list[list[Path]], list[tuple[Path, str]]]:
    """
    Find byte-identical files using size + SHA-256.

    Returns ``(groups, errors)``. Each duplicate group contains at least two
    paths. Files with unique sizes are never hashed, which keeps large scans
    reasonably fast. The caller may cancel between files.
    """
    by_size: dict[int, list[Path]] = defaultdict(list)
    errors: list[tuple[Path, str]] = []

    for raw_path in paths:
        path = Path(raw_path)
        try:
            by_size[path.stat().st_size].append(path)
        except OSError as error:
            errors.append((path, str(error)))

    candidates = sorted(
        (path for group in by_size.values() if len(group) > 1 for path in group),
        key=lambda item: str(item).casefold(),
    )
    total = len(candidates)
    by_digest: dict[tuple[int, str], list[Path]] = defaultdict(list)

    for index, path in enumerate(candidates, start=1):
        if should_cancel is not None and should_cancel():
            raise DuplicateScanCancelled("El análisis de duplicados fue cancelado.")
        if progress is not None:
            progress(index, total, path)
        try:
            size = path.stat().st_size
            digest = sha256_file(path)
            by_digest[(size, digest)].append(path)
        except OSError as error:
            errors.append((path, str(error)))

    groups = [
        sorted(group, key=lambda item: str(item).casefold())
        for group in by_digest.values()
        if len(group) > 1
    ]
    groups.sort(key=lambda group: str(group[0]).casefold())
    return groups, errors
