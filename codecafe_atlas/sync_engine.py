from __future__ import annotations

import csv
import json
import shutil
import sqlite3
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .database import Database

# The homologator works directly with the clean v3 storage model.  Legacy databases
# are converted only on a temporary copy before comparison; the selected external
# file is never modified.
SYNC_TABLES = (
    "buildings",
    "people",
    "dependencies",
    "offices",
    "dependency_people",
    "equipment",
    "counter_records",
    "service_orders",
    "service_formats",
)

CANONICAL_TABLE = {
    "buildings": "atlas_buildings",
    "people": "atlas_people",
    "dependencies": "atlas_dependencies",
    "offices": "atlas_offices",
    "dependency_people": "atlas_dependency_people",
    "equipment": "atlas_equipment",
    "counter_records": "atlas_counter_readings",
    "service_orders": "atlas_service_orders",
    "service_formats": "service_formats",
}

SYNC_IDENTITY_TYPE = {
    "buildings": "buildings",
    "dependencies": "dependencies",
    "equipment": "equipment",
    "counter_records": "counter_records",
    "service_orders": "service_orders",
}

# Parent references must be translated from the external database IDs to the local
# IDs created or matched earlier in the same transaction.
PARENTS = {
    "dependencies": {"building_id": "buildings"},
    "offices": {"dependency_id": "dependencies"},
    "dependency_people": {"dependency_id": "dependencies", "person_id": "people"},
    "equipment": {
        "dependency_id": "dependencies",
        "office_id": "offices",
        "assigned_person_id": "people",
    },
    "counter_records": {"equipment_id": "equipment"},
    "service_orders": {"equipment_id": "equipment", "dependency_id": "dependencies"},
}

IGNORED = {"id", "created_at", "updated_at"}

TABLE_LABELS = {
    "buildings": "Edificios",
    "people": "Personas / CTA",
    "dependencies": "Dependencias",
    "offices": "Oficinas",
    "dependency_people": "Responsables de dependencia",
    "equipment": "Equipos",
    "counter_records": "Contadores",
    "service_orders": "Cédulas de servicio",
    "service_formats": "Formatos de servicio",
}


@dataclass
class SyncItem:
    table: str
    status: str
    record_uuid: str
    identifier: str
    detail: str
    local_id: int | None = None
    external_id: int | None = None
    duplicate_local_id: int | None = None
    local_payload: dict[str, Any] = field(default_factory=dict)
    external_payload: dict[str, Any] = field(default_factory=dict)
    decision: str = ""


@dataclass
class SyncPlan:
    local_path: Path
    external_original: Path
    external_prepared: Path
    items: list[SyncItem]
    summary: dict[str, dict[str, int]]
    compatibility_note: str = ""
    _temporary: Any = None

    def close(self) -> None:
        if self._temporary is not None:
            self._temporary.cleanup()
            self._temporary = None


class SyncEngine:
    def __init__(self, local_path: Path, external_path: Path):
        self.local_path = Path(local_path)
        self.external_path = Path(external_path)

    @staticmethod
    def connect(path: Path, ro: bool = False) -> sqlite3.Connection:
        if ro:
            connection = sqlite3.connect(f"file:{Path(path)}?mode=ro", uri=True)
        else:
            connection = sqlite3.connect(path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    @staticmethod
    def tables(connection: sqlite3.Connection) -> set[str]:
        return {str(row[0]) for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}

    @staticmethod
    def cols(connection: sqlite3.Connection, table: str) -> list[str]:
        return [str(row[1]) for row in connection.execute(f'PRAGMA table_info("{table}")')]

    @staticmethod
    def norm(value: Any) -> Any:
        if isinstance(value, str):
            return " ".join(value.strip().casefold().split())
        return value

    @staticmethod
    def _is_clean(connection: sqlite3.Connection) -> bool:
        return (
            int(connection.execute("PRAGMA user_version").fetchone()[0]) >= 3
            and "atlas_buildings" in SyncEngine.tables(connection)
            and "atlas_sync_records" in SyncEngine.tables(connection)
        )

    def validate_clean(self, path: Path, label: str) -> None:
        try:
            with self.connect(path, True) as connection:
                integrity = connection.execute("PRAGMA integrity_check").fetchone()
                if not integrity or str(integrity[0]).lower() != "ok":
                    raise ValueError(f"La base {label} no superó integrity_check.")
                fk = list(connection.execute("PRAGMA foreign_key_check"))
                if fk:
                    raise ValueError(f"La base {label} contiene {len(fk)} relación(es) inválida(s).")
                if not self._is_clean(connection):
                    raise ValueError(f"La base {label} no utiliza el esquema limpio actual de Atlas.")
                missing = [CANONICAL_TABLE[t] for t in SYNC_TABLES if CANONICAL_TABLE[t] not in self.tables(connection)]
                if missing:
                    raise ValueError(f"La base {label} no es compatible. Faltan tablas: {', '.join(missing)}")
        except sqlite3.Error as exc:
            raise ValueError(f"No se pudo leer la base {label}: {exc}") from exc

    def prepare(self) -> tuple[Path, tempfile.TemporaryDirectory[str] | None, str]:
        if not self.external_path.exists():
            raise ValueError("La base externa seleccionada no existe.")
        if self.external_path.resolve() == self.local_path.resolve():
            raise ValueError("La base externa debe ser diferente de la base local.")

        self.validate_clean(self.local_path, "local")

        try:
            self.validate_clean(self.external_path, "externa")
            return self.external_path, None, ""
        except ValueError:
            # Compatibility is deliberately performed on a copy. Database() invokes
            # the official clean migration and creates the sync identity records.
            temporary = tempfile.TemporaryDirectory(prefix="codecafe_atlas_homologacion_")
            prepared = Path(temporary.name) / self.external_path.name
            try:
                shutil.copy2(self.external_path, prepared)
                Database(prepared)
                self.validate_clean(prepared, "externa preparada")
            except Exception:
                temporary.cleanup()
                raise
            return (
                prepared,
                temporary,
                "La base externa era de una versión anterior. Atlas preparó una copia temporal "
                "con el esquema limpio actual; el archivo externo original no fue modificado.",
            )

    @staticmethod
    def payload(row: sqlite3.Row, columns: list[str]) -> dict[str, Any]:
        return {column: row[column] for column in columns if column not in IGNORED}

    @staticmethod
    def _sync_uuid(connection: sqlite3.Connection, table: str, entity_id: int) -> str:
        entity_type = SYNC_IDENTITY_TYPE.get(table)
        if not entity_type:
            return ""
        row = connection.execute(
            "SELECT record_uuid FROM atlas_sync_records WHERE entity_type=? AND entity_id=?",
            (entity_type, entity_id),
        ).fetchone()
        return str(row[0] or "").strip() if row else ""

    @staticmethod
    def _building_name(connection: sqlite3.Connection, building_id: int | None) -> str:
        if building_id is None:
            return ""
        row = connection.execute("SELECT name FROM atlas_buildings WHERE id=?", (building_id,)).fetchone()
        return str(row[0] or "") if row else ""

    @staticmethod
    def _dependency_name(connection: sqlite3.Connection, dependency_id: int | None) -> str:
        if dependency_id is None:
            return ""
        row = connection.execute("SELECT name FROM atlas_dependencies WHERE id=?", (dependency_id,)).fetchone()
        return str(row[0] or "") if row else ""

    @staticmethod
    def _person_name(connection: sqlite3.Connection, person_id: int | None) -> str:
        if person_id is None:
            return ""
        row = connection.execute("SELECT full_name FROM atlas_people WHERE id=?", (person_id,)).fetchone()
        return str(row[0] or "") if row else ""

    def natural_key(self, connection: sqlite3.Connection, table: str, row: sqlite3.Row) -> tuple[Any, ...] | None:
        n = self.norm
        if table == "buildings":
            value = n(row["name"])
            return (value,) if value else None
        if table == "people":
            value = n(row["full_name"])
            return (value,) if value else None
        if table == "dependencies":
            return (
                n(self._building_name(connection, row["building_id"])),
                n(row["name"]),
                n(row["floor"]),
            )
        if table == "offices":
            return (n(self._dependency_name(connection, row["dependency_id"])), n(row["name"]))
        if table == "dependency_people":
            return (
                n(self._dependency_name(connection, row["dependency_id"])),
                n(self._person_name(connection, row["person_id"])),
                n(row["role"]),
            )
        if table == "equipment":
            for key in ("serial_number", "inventory_number", "hostname"):
                value = n(row[key])
                if value:
                    return (key, value)
            return None
        if table == "counter_records":
            value = n(row["external_uid"])
            return (value,) if value else None
        if table == "service_orders":
            # UUID is authoritative. This natural key is only duplicate protection
            # for records that originated before homologation identity existed.
            folio = n(row["folio"])
            provider = n(row["provider_report"])
            dgti = n(row["dgti_report"])
            if folio or provider or dgti:
                return (folio, provider, dgti)
            return None
        if table == "service_formats":
            value = n(row["name"])
            return (value,) if value else None
        return None

    def identifier(self, connection: sqlite3.Connection, table: str, row: sqlite3.Row) -> str:
        if table == "buildings":
            return str(row["name"])
        if table == "people":
            return str(row["full_name"])
        if table == "dependencies":
            building = self._building_name(connection, row["building_id"])
            return " · ".join(x for x in (str(row["name"]), building, str(row["floor"] or "")) if x)
        if table == "offices":
            return " · ".join(x for x in (str(row["name"]), self._dependency_name(connection, row["dependency_id"])) if x)
        if table == "dependency_people":
            return " · ".join(
                x for x in (
                    self._person_name(connection, row["person_id"]),
                    str(row["role"]),
                    self._dependency_name(connection, row["dependency_id"]),
                ) if x
            )
        if table == "equipment":
            return " · ".join(str(row[k]) for k in ("serial_number", "inventory_number", "model") if row[k] not in (None, ""))
        if table == "counter_records":
            return " · ".join(str(row[k]) for k in ("serial_snapshot", "reading_date", "total_prints") if row[k] not in (None, ""))
        if table == "service_orders":
            return " · ".join(str(row[k]) for k in ("folio", "provider_report") if row[k] not in (None, ""))
        if table == "service_formats":
            return str(row["name"])
        return str(row["id"])

    def _dependency_token(self, connection: sqlite3.Connection, dependency_id: int | None) -> tuple[Any, ...]:
        if dependency_id is None:
            return ("", "", "")
        row = connection.execute(
            "SELECT building_id,name,floor FROM atlas_dependencies WHERE id=?", (dependency_id,)
        ).fetchone()
        if row is None:
            return ("", "", "")
        return (
            self.norm(self._building_name(connection, row["building_id"])),
            self.norm(row["name"]),
            self.norm(row["floor"]),
        )

    def _equipment_token(self, connection: sqlite3.Connection, equipment_id: int | None) -> tuple[Any, ...]:
        if equipment_id is None:
            return ("", "")
        row = connection.execute(
            "SELECT serial_number,inventory_number,hostname FROM atlas_equipment WHERE id=?", (equipment_id,)
        ).fetchone()
        if row is None:
            return ("", "")
        for key in ("serial_number", "inventory_number", "hostname"):
            value = self.norm(row[key])
            if value:
                return (key, value)
        return ("", "")

    def comparison_payload(
        self, connection: sqlite3.Connection, table: str, row: sqlite3.Row, columns: list[str]
    ) -> dict[str, Any]:
        payload = self.payload(row, columns)
        if table == "dependencies" and "building_id" in payload:
            payload["building_id"] = self.norm(self._building_name(connection, row["building_id"]))
        elif table == "offices" and "dependency_id" in payload:
            payload["dependency_id"] = self._dependency_token(connection, row["dependency_id"])
        elif table == "dependency_people":
            if "dependency_id" in payload:
                payload["dependency_id"] = self._dependency_token(connection, row["dependency_id"])
            if "person_id" in payload:
                payload["person_id"] = self.norm(self._person_name(connection, row["person_id"]))
        elif table == "equipment":
            if "dependency_id" in payload:
                payload["dependency_id"] = self._dependency_token(connection, row["dependency_id"])
            if "office_id" in payload:
                office = connection.execute("SELECT name FROM atlas_offices WHERE id=?", (row["office_id"],)).fetchone() if row["office_id"] is not None else None
                payload["office_id"] = self.norm(office[0]) if office else ""
            if "assigned_person_id" in payload:
                payload["assigned_person_id"] = self.norm(self._person_name(connection, row["assigned_person_id"]))
        elif table == "counter_records" and "equipment_id" in payload:
            payload["equipment_id"] = self._equipment_token(connection, row["equipment_id"])
        elif table == "service_orders":
            if "equipment_id" in payload:
                payload["equipment_id"] = self._equipment_token(connection, row["equipment_id"])
            if "dependency_id" in payload:
                payload["dependency_id"] = self._dependency_token(connection, row["dependency_id"])
        return payload

    @staticmethod
    def _normalized_payload(payload: dict[str, Any]) -> dict[str, Any]:
        return {key: SyncEngine.norm(value) for key, value in payload.items()}

    @staticmethod
    def _difference(local_payload: dict[str, Any], external_payload: dict[str, Any]) -> str:
        left = SyncEngine._normalized_payload(local_payload)
        right = SyncEngine._normalized_payload(external_payload)
        changed = [key for key in sorted(set(left) | set(right)) if left.get(key) != right.get(key)]
        return ", ".join(changed[:10]) + ("…" if len(changed) > 10 else "")

    def analyze(self) -> SyncPlan:
        external_prepared, temporary, note = self.prepare()
        items: list[SyncItem] = []
        summary: dict[str, dict[str, int]] = {}

        with self.connect(self.local_path, True) as local, self.connect(external_prepared, True) as external:
            for table in SYNC_TABLES:
                physical = CANONICAL_TABLE[table]
                local_cols = self.cols(local, physical)
                external_cols = self.cols(external, physical)
                common = [col for col in local_cols if col in set(external_cols)]
                query_cols = ", ".join(f'"{col}"' for col in common)
                if table == "dependency_people":
                    # The relation table uses a composite primary key and has no public id.
                    # rowid is used only as a transient handle during this homologation run.
                    local_rows = list(local.execute(f'SELECT rowid AS id, {query_cols} FROM "{physical}"'))
                    external_rows = list(external.execute(f'SELECT rowid AS id, {query_cols} FROM "{physical}"'))
                    common = ["id", *common]
                else:
                    local_rows = list(local.execute(f'SELECT {query_cols} FROM "{physical}"'))
                    external_rows = list(external.execute(f'SELECT {query_cols} FROM "{physical}"'))

                # UUID matching is used for entities with durable sync identity.
                local_uuid: dict[str, sqlite3.Row] = {}
                external_uuid: dict[str, sqlite3.Row] = {}
                if table in SYNC_IDENTITY_TYPE:
                    for row in local_rows:
                        value = self._sync_uuid(local, table, int(row["id"]))
                        if value:
                            local_uuid[value] = row
                    for row in external_rows:
                        value = self._sync_uuid(external, table, int(row["id"]))
                        if value:
                            external_uuid[value] = row

                local_natural: dict[tuple[Any, ...], sqlite3.Row] = {}
                for row in local_rows:
                    key = self.natural_key(local, table, row)
                    if key is not None:
                        local_natural.setdefault(key, row)

                counts = {"nuevos": 0, "coincidentes": 0, "conflictos": 0, "duplicados": 0, "solo_local": 0}
                matched_local_ids: set[int] = set()

                for external_row in external_rows:
                    external_id = int(external_row["id"]) if "id" in external_row.keys() else None
                    record_uuid = self._sync_uuid(external, table, external_id) if table in SYNC_IDENTITY_TYPE and external_id is not None else ""
                    local_row = local_uuid.get(record_uuid) if record_uuid else None
                    natural = self.natural_key(external, table, external_row)
                    duplicate = local_natural.get(natural) if natural is not None else None
                    # Entities without a dedicated sync UUID are identified by their
                    # canonical natural key, not treated as duplicates merely because
                    # they exist on both databases.
                    if table not in SYNC_IDENTITY_TYPE and local_row is None and duplicate is not None:
                        local_row = duplicate
                        duplicate = None
                    identifier = self.identifier(external, table, external_row)

                    if local_row is None and duplicate is not None:
                        counts["duplicados"] += 1
                        matched_local_ids.add(int(duplicate["id"]) if "id" in duplicate.keys() else hash(natural))
                        items.append(
                            SyncItem(
                                table,
                                "Posible duplicado",
                                record_uuid,
                                identifier,
                                "Misma identidad funcional con origen distinto. Atlas no creará otro registro automáticamente.",
                                None,
                                external_id,
                                int(duplicate["id"]) if "id" in duplicate.keys() else None,
                                self.payload(duplicate, common),
                                self.payload(external_row, common),
                                "Conservar local",
                            )
                        )
                        continue

                    if local_row is None:
                        counts["nuevos"] += 1
                        items.append(
                            SyncItem(
                                table,
                                "Nuevo externo",
                                record_uuid,
                                identifier,
                                "No existe en la base local.",
                                None,
                                external_id,
                                None,
                                {},
                                self.payload(external_row, common),
                                "Importar",
                            )
                        )
                        continue

                    local_id = int(local_row["id"]) if "id" in local_row.keys() else None
                    if local_id is not None:
                        matched_local_ids.add(local_id)
                    local_payload = self.comparison_payload(local, table, local_row, common)
                    external_payload = self.comparison_payload(external, table, external_row, common)
                    if self._normalized_payload(local_payload) == self._normalized_payload(external_payload):
                        counts["coincidentes"] += 1
                        status, decision, detail = "Coincidente", "Sin cambios", "Misma identidad y mismo contenido."
                    else:
                        counts["conflictos"] += 1
                        status, decision = "Conflicto", "Conservar local"
                        detail = "Campos distintos: " + self._difference(local_payload, external_payload)
                    items.append(
                        SyncItem(
                            table,
                            status,
                            record_uuid,
                            identifier,
                            detail,
                            local_id,
                            external_id,
                            None,
                            local_payload,
                            external_payload,
                            decision,
                        )
                    )

                # Local-only rows are informational and are never deleted by homologation.
                for local_row in local_rows:
                    local_id = int(local_row["id"]) if "id" in local_row.keys() else None
                    if local_id is not None and local_id in matched_local_ids:
                        continue
                    local_record_uuid = self._sync_uuid(local, table, local_id) if table in SYNC_IDENTITY_TYPE and local_id is not None else ""
                    if local_record_uuid and local_record_uuid in external_uuid:
                        continue
                    local_key = self.natural_key(local, table, local_row)
                    if local_key is not None:
                        # If an external row already matched this key as duplicate, it is not local-only.
                        if any(x.table == table and x.duplicate_local_id == local_id for x in items):
                            continue
                    counts["solo_local"] += 1
                    items.append(
                        SyncItem(
                            table,
                            "Solo local",
                            local_record_uuid,
                            self.identifier(local, table, local_row),
                            "No existe en la base externa. Se conserva sin cambios.",
                            local_id,
                            None,
                            None,
                            self.payload(local_row, common),
                            {},
                            "Conservar local",
                        )
                    )
                summary[table] = counts

        return SyncPlan(self.local_path, self.external_path, external_prepared, items, summary, note, temporary)

    def _backup(self) -> Path:
        directory = self.local_path.parent.parent / "backups"
        directory.mkdir(parents=True, exist_ok=True)
        backup = directory / f"atlas_pre_homologacion_{datetime.now():%Y-%m-%d_%H%M%S}.db"
        with self.connect(self.local_path, True) as source, sqlite3.connect(backup) as destination:
            source.backup(destination)
        self.validate_clean(backup, "respaldo")
        return backup

    @staticmethod
    def _upsert_sync_identity(
        connection: sqlite3.Connection,
        table: str,
        entity_id: int,
        record_uuid: str,
        external_connection: sqlite3.Connection,
        external_id: int,
    ) -> None:
        entity_type = SYNC_IDENTITY_TYPE.get(table)
        if not entity_type:
            return
        source = external_connection.execute(
            "SELECT record_uuid,revision,created_by_installation,updated_by_installation,deleted_at "
            "FROM atlas_sync_records WHERE entity_type=? AND entity_id=?",
            (entity_type, external_id),
        ).fetchone()
        if source is None:
            values = (record_uuid or str(uuid.uuid4()), 1, "", "", None)
        else:
            values = (
                str(source["record_uuid"] or record_uuid or uuid.uuid4()),
                int(source["revision"] or 1),
                str(source["created_by_installation"] or ""),
                str(source["updated_by_installation"] or ""),
                source["deleted_at"],
            )
        connection.execute(
            "INSERT INTO atlas_sync_records(entity_type,entity_id,record_uuid,revision,created_by_installation,updated_by_installation,deleted_at) "
            "VALUES(?,?,?,?,?,?,?) "
            "ON CONFLICT(entity_type,entity_id) DO UPDATE SET "
            "record_uuid=excluded.record_uuid, revision=MAX(atlas_sync_records.revision,excluded.revision), "
            "updated_by_installation=excluded.updated_by_installation, deleted_at=excluded.deleted_at",
            (entity_type, entity_id, *values),
        )

    def apply(self, plan: SyncPlan, report_dir: Path | None = None):
        start = time.time()
        backup = self._backup()
        stats = {"insertados": 0, "actualizados": 0, "omitidos": 0, "coincidentes": 0}
        actions: list[tuple[str, str, str]] = []
        id_map: dict[str, dict[int, int]] = {table: {} for table in SYNC_TABLES}

        try:
            with self.connect(self.local_path) as local, self.connect(plan.external_prepared, True) as external:
                local.execute("BEGIN IMMEDIATE")

                for table in SYNC_TABLES:
                    physical = CANONICAL_TABLE[table]
                    local_cols = self.cols(local, physical)
                    external_cols = self.cols(external, physical)
                    common = [col for col in external_cols if col in local_cols and col != "id"]
                    table_items = [item for item in plan.items if item.table == table and item.external_id is not None]

                    for item in table_items:
                        if table == "dependency_people":
                            external_row = external.execute(
                                f'SELECT rowid AS id, * FROM "{physical}" WHERE rowid=?', (item.external_id,)
                            ).fetchone()
                        else:
                            external_row = external.execute(
                                f'SELECT * FROM "{physical}" WHERE id=?', (item.external_id,)
                            ).fetchone()
                        if external_row is None:
                            raise ValueError(f"El registro externo ya no existe: {TABLE_LABELS[table]} · {item.identifier}")

                        if item.status == "Coincidente":
                            stats["coincidentes"] += 1
                            if item.local_id is not None:
                                id_map[table][item.external_id] = item.local_id
                            continue

                        if item.decision in ("Conservar local", "Ignorar", "Sin cambios"):
                            stats["omitidos"] += 1
                            target = item.duplicate_local_id or item.local_id
                            if target is not None:
                                id_map[table][item.external_id] = target
                            actions.append((TABLE_LABELS[table], item.identifier, item.decision))
                            continue

                        values = {column: external_row[column] for column in common}
                        for fk, parent_table in PARENTS.get(table, {}).items():
                            old_id = values.get(fk)
                            if old_id is None:
                                continue
                            translated = id_map[parent_table].get(int(old_id))
                            if translated is None:
                                raise ValueError(
                                    f"No se pudo traducir la relación {TABLE_LABELS[table]}.{fk} para {item.identifier}. "
                                    f"Revisa primero la decisión del registro padre."
                                )
                            values[fk] = translated

                        target = item.local_id
                        if item.status == "Posible duplicado" and item.decision == "Usar externo":
                            target = item.duplicate_local_id

                        if target is not None and item.decision == "Usar externo":
                            # Identity and primary key remain local; only business fields are updated.
                            sets = ", ".join(f'"{column}"=?' for column in values)
                            key_column = "rowid" if table == "dependency_people" else "id"
                            local.execute(
                                f'UPDATE "{physical}" SET {sets} WHERE {key_column}=?',
                                (*values.values(), target),
                            )
                            new_id = target
                            stats["actualizados"] += 1
                        else:
                            columns = list(values)
                            marks = ", ".join("?" for _ in columns)
                            names = ", ".join(f'"{column}"' for column in columns)
                            cursor = local.execute(
                                f'INSERT INTO "{physical}" ({names}) VALUES ({marks})',
                                tuple(values[column] for column in columns),
                            )
                            new_id = int(cursor.lastrowid)
                            stats["insertados"] += 1
                            if table in SYNC_IDENTITY_TYPE:
                                self._upsert_sync_identity(
                                    local, table, new_id, item.record_uuid, external, int(item.external_id)
                                )

                        id_map[table][int(item.external_id)] = int(new_id)
                        actions.append((TABLE_LABELS[table], item.identifier, item.decision))

                integrity = local.execute("PRAGMA integrity_check").fetchone()[0]
                fk = list(local.execute("PRAGMA foreign_key_check"))
                if str(integrity).lower() != "ok" or fk:
                    raise ValueError(
                        f"Validación final fallida: integrity={integrity}, foreign_keys={len(fk)}"
                    )

                # Explicit duplicate guards aligned with Atlas' data rules.
                duplicate_checks = (
                    ("atlas_buildings", "lower(trim(name))", "edificio"),
                    ("atlas_equipment", "lower(trim(serial_number))", "serie de equipo", "trim(serial_number)<>''"),
                    ("atlas_equipment", "lower(trim(inventory_number))", "inventario de equipo", "trim(inventory_number)<>''"),
                    ("atlas_equipment", "lower(trim(hostname))", "hostname", "trim(hostname)<>''"),
                )
                for check in duplicate_checks:
                    table_name, expression, label, *where = check
                    condition = f" WHERE {where[0]}" if where else ""
                    duplicate = local.execute(
                        f"SELECT {expression},COUNT(*) FROM {table_name}{condition} GROUP BY {expression} HAVING COUNT(*)>1 LIMIT 1"
                    ).fetchone()
                    if duplicate:
                        raise ValueError(f"La homologación produciría un {label} duplicado: {duplicate[0]}")

                local.commit()
        except Exception:
            shutil.copy2(backup, self.local_path)
            raise
        finally:
            plan.close()

        output = Path(report_dir or self.local_path.parent.parent / "reports")
        output.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        data = {
            "version": "1.0.24.16",
            "fecha": datetime.now().isoformat(timespec="seconds"),
            "base_local": str(self.local_path),
            "base_externa": str(self.external_path),
            "respaldo": str(backup),
            "duracion_segundos": round(time.time() - start, 3),
            "resultados": stats,
            "acciones": [
                {"entidad": entity, "registro": identifier, "decision": decision}
                for entity, identifier, decision in actions
            ],
        }
        json_path = output / f"homologacion_{stamp}.json"
        csv_path = output / f"homologacion_{stamp}.csv"
        json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            writer.writerow(["Entidad", "Registro", "Decisión"])
            writer.writerows(actions)
        return data, json_path, csv_path
