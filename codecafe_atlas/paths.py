from __future__ import annotations

import os
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

def _persistent_data_dir() -> Path:
    override = str(os.environ.get("CODECAFE_ATLAS_DATA_DIR", "")).strip()
    if override:
        return Path(override).expanduser().resolve()
    home = Path.home()
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA") or (home / "AppData" / "Roaming"))
        return base / "CodeCafe-Atlas" / "data"
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "CodeCafe-Atlas" / "data"
    base = Path(os.environ.get("XDG_DATA_HOME") or (home / ".local" / "share"))
    return base / "CodeCafe-Atlas" / "data"

def data_dir() -> Path:
    # Packaged builds must keep operational data outside the versioned program
    # directory. Rebuilding or extracting a new Atlas version must not create a
    # separate empty database or destroy the user's working database.
    path = _persistent_data_dir() if getattr(sys, "frozen", False) else application_root() / "data"
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

def _database_schema_kind(path: Path) -> str:
    """Classify a candidate DB without modifying it.

    Only schemas Atlas actually knows how to open/migrate are accepted here.
    This deliberately avoids treating any DB with a generic ``dependencies``
    table as an Atlas database.
    """
    if not path.is_file() or path.suffix.lower() not in {".db", ".sqlite", ".sqlite3"}:
        return ""
    try:
        c = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
        try:
            tables = {str(r[0]).lower() for r in c.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )}
            user_version = int(c.execute("PRAGMA user_version").fetchone()[0])
            clean_required = {
                "atlas_buildings", "atlas_dependencies", "atlas_equipment",
                "atlas_counter_readings", "atlas_service_orders",
            }
            legacy_required = {"buildings", "locations", "dependencies", "equipment"}
            if clean_required.issubset(tables) and user_version >= 3:
                return "clean"
            if legacy_required.issubset(tables):
                return "legacy-compatible"
            return ""
        finally:
            c.close()
    except sqlite3.Error:
        return ""


def _looks_like_atlas_database(path: Path) -> bool:
    return bool(_database_schema_kind(path))


def _candidate_databases(current: Path) -> list[Path]:
    """Return explicit same-installation DB candidates only.

    A fresh public build must never rummage through sibling Atlas versions and
    silently adopt one of their databases.  Compatibility is preserved for an
    in-place upgrade: any recognized DB intentionally left in this install's
    own ``data`` directory can be adopted when ``atlas.db`` does not yet hold
    data.  Other databases remain available through Administrar datos ->
    Cargar/migrar base de datos existente.
    """
    candidates: list[Path] = []
    for candidate in data_dir().glob("*"):
        if candidate.resolve() == current.resolve():
            continue
        if _looks_like_atlas_database(candidate):
            candidates.append(candidate)
    return candidates


def _migrate_previous_database_if_needed(current: Path) -> None:
    global _LAST_DATABASE_MIGRATION
    if current.exists() and current.stat().st_size > 0:
        # An existing atlas.db is authoritative.  Database.initialize() will
        # validate/migrate it; never replace it behind the user's back.
        return

    ranked = []
    for candidate in _candidate_databases(current):
        counts = _database_counts(candidate)
        total = sum(counts)
        schema_kind = _database_schema_kind(candidate)
        if not schema_kind:
            continue
        ranked.append((candidate.stat().st_mtime, total, candidate, counts, schema_kind))

    if not ranked:
        return

    _, _, source, counts, schema_kind = max(ranked, key=lambda item: (item[0], item[1]))
    current.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, current)
    _LAST_DATABASE_MIGRATION = (
        f"Se adoptó una base Atlas compatible colocada en esta instalación: {source.name}. "
        f"Formato: {schema_kind}. Dependencias: {counts[0]}, equipos: {counts[1]}, "
        f"órdenes: {counts[2]}, contadores: {counts[3]}."
    )

def _legacy_install_database_candidates(current: Path) -> list[Path]:
    """Find prior packaged Atlas databases for one-time migration.

    This is only used when the new persistent database does not yet exist.
    Candidates are read-only, must have a recognized Atlas schema, and are
    copied rather than moved. The source installation is never modified.
    """
    roots: list[Path] = []
    app = application_root()
    for root in (
        app.parent,
        app.parent.parent,
        app.parent.parent.parent,
        Path.home() / "Downloads",
        Path.home() / "Desktop",
    ):
        try:
            resolved = root.resolve()
        except OSError:
            continue
        if resolved not in roots and resolved.exists():
            roots.append(resolved)

    found: list[Path] = []
    seen: set[Path] = set()
    current_resolved = current.resolve()
    for root in roots:
        try:
            iterator = root.rglob("atlas.db")
            for candidate in iterator:
                try:
                    resolved = candidate.resolve()
                except OSError:
                    continue
                if resolved == current_resolved or resolved in seen:
                    continue
                # Limit discovery to Atlas-looking installation paths.
                nearby = "/".join(part.casefold() for part in resolved.parts[-7:])
                if "atlas" not in nearby:
                    continue
                if candidate.parent.name.casefold() != "data":
                    continue
                if _looks_like_atlas_database(candidate):
                    seen.add(resolved)
                    found.append(candidate)
        except OSError:
            continue
    return found

def _migrate_previous_install_database_if_needed(current: Path) -> None:
    global _LAST_DATABASE_MIGRATION
    if current.exists() and current.stat().st_size > 0:
        return
    ranked = []
    for candidate in _legacy_install_database_candidates(current):
        counts = _database_counts(candidate)
        schema_kind = _database_schema_kind(candidate)
        if not schema_kind:
            continue
        # Prefer the database with the most registered equipment, then the most
        # total operational records, then the newest file. This avoids adopting
        # a fresh/test build when a fuller working Atlas database is available.
        ranked.append((counts[1], sum(counts), candidate.stat().st_mtime, candidate, counts, schema_kind))
    if not ranked:
        return
    _, _, _, source, counts, schema_kind = max(ranked, key=lambda item: (item[0], item[1], item[2]))
    current.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, current)
    _LAST_DATABASE_MIGRATION = (
        f"Se recuperó la base operativa de una instalación anterior: {source}. "
        f"Formato: {schema_kind}. Dependencias: {counts[0]}, equipos: {counts[1]}, "
        f"órdenes: {counts[2]}, contadores: {counts[3]}. "
        f"Desde ahora Atlas conservará esta base en {current}."
    )

def database_path() -> Path:
    path = data_dir() / "atlas.db"
    if getattr(sys, "frozen", False):
        _migrate_previous_install_database_if_needed(path)
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
    path = (data_dir().parent / "backups") if getattr(sys, "frozen", False) else (application_root() / "backups")
    path.mkdir(parents=True, exist_ok=True)
    return path
