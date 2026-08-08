from __future__ import annotations

import re
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from .identity import PRODUCT_NAME

APP_NAME = PRODUCT_NAME
_LAST_DATABASE_MIGRATION = ""

def application_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent

def bundled_root() -> Path:
    bundle = getattr(sys, "_MEIPASS", None)
    return Path(bundle).resolve() if bundle else application_root()

def asset_path(name: str) -> Path:
    return bundled_root() / "assets" / name

def data_dir() -> Path:
    path = application_root() / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path

def _database_counts(path: Path) -> tuple[int, int, int, int]:
    if not path.exists() or path.stat().st_size == 0:
        return 0, 0, 0, 0
    try:
        connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
        try:
            names = {str(r[0]).lower() for r in connection.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view')")}
            counts = []
            for table in ("dependencies", "equipment", "service_orders", "counter_records"):
                if table in names:
                    counts.append(int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]))
                else:
                    counts.append(0)
            return tuple(counts)
        finally:
            connection.close()
    except sqlite3.Error:
        return 0, 0, 0, 0

def _looks_like_atlas_database(path: Path) -> bool:
    if not path.is_file() or path.suffix.lower() not in {".db", ".sqlite", ".sqlite3"}:
        return False
    try:
        c = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
        try:
            names = {str(r[0]).lower() for r in c.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view')")}
            return bool({"atlas_equipment", "equipment", "dependencies"} & names)
        finally:
            c.close()
    except sqlite3.Error:
        return False

def _candidate_databases(current: Path) -> list[Path]:
    root = application_root()
    parent = root.parent
    candidates: list[Path] = []

    # First, accept any compatible database already placed in this installation's data folder.
    for candidate in data_dir().glob("*"):
        if candidate.resolve() != current.resolve() and _looks_like_atlas_database(candidate):
            candidates.append(candidate)

    # Then inspect sibling portable installations without depending on historical product names.
    if parent.exists():
        for folder in parent.iterdir():
            if not folder.is_dir() or folder.resolve() == root.resolve():
                continue
            folder_data = folder / "data"
            if not folder_data.is_dir():
                continue
            for candidate in folder_data.glob("*"):
                if candidate.resolve() != current.resolve() and _looks_like_atlas_database(candidate):
                    candidates.append(candidate)

    # Optional current-brand shared-data folders.
    for shared_name in ("CodeCafe Atlas Data", "CodeCafe_Atlas_Data"):
        shared = parent / shared_name
        if not shared.is_dir():
            continue
        for candidate in shared.glob("*"):
            if candidate.resolve() != current.resolve() and _looks_like_atlas_database(candidate):
                candidates.append(candidate)

    # Preserve deterministic order while removing duplicate resolved paths.
    unique: dict[Path, Path] = {}
    for candidate in candidates:
        unique[candidate.resolve()] = candidate
    return list(unique.values())

def _migrate_previous_database_if_needed(current: Path) -> None:
    global _LAST_DATABASE_MIGRATION
    if sum(_database_counts(current)) > 0:
        return

    ranked = []
    for candidate in _candidate_databases(current):
        counts = _database_counts(candidate)
        total = sum(counts)
        if total <= 0:
            continue
        folder_name = candidate.parents[1].name if len(candidate.parents) > 1 else ""
        match = re.search(r"v(\d+(?:\.\d+)*)", folder_name, flags=re.IGNORECASE)
        version = tuple(int(part) for part in match.group(1).split(".")) if match else (-1,)
        ranked.append((version, candidate.stat().st_mtime, total, candidate, counts))

    if not ranked:
        return

    _, _, _, source, counts = max(ranked, key=lambda item: (item[0], item[1], item[2]))
    current.parent.mkdir(parents=True, exist_ok=True)
    if current.exists() and current.stat().st_size > 0:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        shutil.copy2(current, current.with_name(f"atlas_antes_de_migrar_{stamp}.db"))
    shutil.copy2(source, current)
    _LAST_DATABASE_MIGRATION = (
        f"Se recuperó automáticamente una base Atlas compatible desde {source}. "
        f"Dependencias: {counts[0]}, equipos: {counts[1]}, órdenes: {counts[2]}, contadores: {counts[3]}."
    )

def database_path() -> Path:
    path = data_dir() / "atlas.db"
    _migrate_previous_database_if_needed(path)
    return path

def database_migration_message() -> str:
    return _LAST_DATABASE_MIGRATION

def module_dir(name: str) -> Path:
    destination = application_root() / "modules" / name
    if not destination.exists():
        source = bundled_root() / "modules" / name
        if source.exists() and source != destination:
            shutil.copytree(source, destination, dirs_exist_ok=True)
    destination.mkdir(parents=True, exist_ok=True)
    return destination

def dashboard_dir() -> Path:
    path = data_dir() / "dashboard"
    path.mkdir(parents=True, exist_ok=True)
    return path

def backups_dir() -> Path:
    path = application_root() / "backups"
    path.mkdir(parents=True, exist_ok=True)
    return path
