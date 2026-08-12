from __future__ import annotations

import re
import shutil
import unicodedata
from difflib import SequenceMatcher
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from .clean_database import ensure_clean_database


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS buildings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL COLLATE NOCASE UNIQUE,
    address TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS locations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    building_id INTEGER,
    building TEXT NOT NULL DEFAULT '',
    city TEXT NOT NULL DEFAULT '',
    state TEXT NOT NULL DEFAULT '',
    street TEXT NOT NULL DEFAULT '',
    exterior_number TEXT NOT NULL DEFAULT '',
    colony TEXT NOT NULL DEFAULT '',
    postal_code TEXT NOT NULL DEFAULT '',
    floor TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(building_id) REFERENCES buildings(id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS dependencies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    location_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    court TEXT NOT NULL DEFAULT '',
    tribunal TEXT NOT NULL DEFAULT '',
    office TEXT NOT NULL DEFAULT '',
    cta TEXT NOT NULL DEFAULT '',
    phone TEXT NOT NULL DEFAULT '',
    email TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(location_id) REFERENCES locations(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS equipment (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dependency_id INTEGER NOT NULL,
    equipment_type TEXT NOT NULL DEFAULT '',
    brand TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT '',
    serial_number TEXT NOT NULL DEFAULT '',
    inventory_number TEXT NOT NULL DEFAULT '',
    assigned_user TEXT NOT NULL DEFAULT '',
    ip_address TEXT NOT NULL DEFAULT '',
    hostname TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'Activo',
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(dependency_id) REFERENCES dependencies(id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_buildings_name ON buildings(name);
CREATE INDEX IF NOT EXISTS idx_locations_building ON locations(building);
CREATE INDEX IF NOT EXISTS idx_dependencies_name ON dependencies(name);
CREATE INDEX IF NOT EXISTS idx_dependencies_location ON dependencies(location_id);
CREATE INDEX IF NOT EXISTS idx_dependencies_active ON dependencies(active);
CREATE INDEX IF NOT EXISTS idx_equipment_dependency ON equipment(dependency_id);
CREATE INDEX IF NOT EXISTS idx_equipment_serial ON equipment(serial_number);
CREATE INDEX IF NOT EXISTS idx_equipment_hostname ON equipment(hostname);

CREATE TABLE IF NOT EXISTS service_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    folio TEXT NOT NULL DEFAULT '',
    document_type TEXT NOT NULL DEFAULT 'Cédula de Servicio',
    equipment_id INTEGER,
    dependency_id INTEGER,
    dgti_report TEXT NOT NULL DEFAULT '',
    provider_report TEXT NOT NULL DEFAULT '',
    report_date TEXT NOT NULL DEFAULT '',
    report_time TEXT NOT NULL DEFAULT '',
    responsible_name TEXT NOT NULL DEFAULT '',
    validator_name TEXT NOT NULL DEFAULT '',
    validator_role TEXT NOT NULL DEFAULT '',
    validator_phone TEXT NOT NULL DEFAULT '',
    movement_type TEXT NOT NULL DEFAULT '',
    reported_issue TEXT NOT NULL DEFAULT '',
    diagnosis TEXT NOT NULL DEFAULT '',
    diagnosis_date TEXT NOT NULL DEFAULT '',
    diagnosis_time TEXT NOT NULL DEFAULT '',
    solution TEXT NOT NULL DEFAULT '',
    solution_date TEXT NOT NULL DEFAULT '',
    solution_time TEXT NOT NULL DEFAULT '',
    service_notes TEXT NOT NULL DEFAULT '',
    technician_name TEXT NOT NULL DEFAULT '',
    equipment_operates TEXT NOT NULL DEFAULT '',
    equipment_condition TEXT NOT NULL DEFAULT '',
    output_path TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(equipment_id) REFERENCES equipment(id) ON DELETE SET NULL,
    FOREIGN KEY(dependency_id) REFERENCES dependencies(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_service_orders_folio ON service_orders(folio);
CREATE INDEX IF NOT EXISTS idx_service_orders_equipment ON service_orders(equipment_id);

CREATE TABLE IF NOT EXISTS counter_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_uid TEXT NOT NULL UNIQUE,
    equipment_id INTEGER,
    reading_date TEXT NOT NULL DEFAULT '',
    serial_number TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT '',
    source_file TEXT NOT NULL DEFAULT '',
    total_prints REAL,
    office_prints REAL,
    letter_prints REAL,
    duplex_sheets REAL,
    jam_events REAL,
    misfeed_events REAL,
    economode_prints REAL,
    format_type TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(equipment_id) REFERENCES equipment(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_counter_records_uid
    ON counter_records(record_uid);
CREATE INDEX IF NOT EXISTS idx_counter_records_serial
    ON counter_records(serial_number);
CREATE INDEX IF NOT EXISTS idx_counter_records_date
    ON counter_records(reading_date);
CREATE INDEX IF NOT EXISTS idx_counter_records_equipment_date
    ON counter_records(equipment_id, reading_date DESC, id DESC);


CREATE TABLE IF NOT EXISTS service_formats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL COLLATE NOCASE UNIQUE,
    document_type TEXT NOT NULL DEFAULT 'Cédula de Servicio',
    description TEXT NOT NULL DEFAULT '',
    validator_name TEXT NOT NULL DEFAULT '',
    validator_role TEXT NOT NULL DEFAULT '',
    validator_phone TEXT NOT NULL DEFAULT '',
    movement_type TEXT NOT NULL DEFAULT '',
    reported_issue TEXT NOT NULL DEFAULT '',
    diagnosis TEXT NOT NULL DEFAULT '',
    solution TEXT NOT NULL DEFAULT '',
    service_notes TEXT NOT NULL DEFAULT '',
    technician_name TEXT NOT NULL DEFAULT '',
    equipment_operates TEXT NOT NULL DEFAULT 'Sí',
    equipment_condition TEXT NOT NULL DEFAULT 'No',
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_service_formats_name
    ON service_formats(name);
CREATE INDEX IF NOT EXISTS idx_service_formats_active
    ON service_formats(active);

CREATE TABLE IF NOT EXISTS app_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sync_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

"""


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def initialize(self) -> None:
        ensure_clean_database(self.path)
        with self.connect() as connection:
            # The clean schema is created/migrated by clean_database.py.
            # Existing Database methods operate through non-storing compatibility views.
            if connection.execute("PRAGMA user_version").fetchone()[0] >= 3:
                connection.execute("PRAGMA foreign_keys = ON")
                self._initialize_service_formats(connection)
                connection.execute("PRAGMA optimize")
                return
            connection.executescript(SCHEMA)
            self._ensure_column(connection, "locations", "building_id", "INTEGER")
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_locations_building_id ON locations(building_id)"
            )
            self._ensure_column(connection, "equipment", "inventory_number", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(connection, "equipment", "assigned_user", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(connection, "service_orders", "diagnosis_date", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(connection, "service_orders", "diagnosis_time", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(connection, "service_orders", "solution_date", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(connection, "service_orders", "solution_time", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(connection, "service_orders", "equipment_operates", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(connection, "service_orders", "equipment_condition", "TEXT NOT NULL DEFAULT ''")
            self._initialize_application_metadata(connection)
            self._initialize_service_formats(connection)
            self._prepare_sync_identity(connection)
            self._synchronize_buildings(connection)
            connection.execute("PRAGMA optimize")

    def _initialize_application_metadata(self, connection: sqlite3.Connection) -> None:
        fixed = {
            "application_family": "CodeCafe Atlas",
            "application_id": "io.codecafe.atlas",
            "origin_id": "CCA-JSS-2026",
            "database_format": "codecafe-atlas",
            "schema_version": "1",
        }
        for key, value in fixed.items():
            connection.execute(
                "INSERT OR IGNORE INTO app_metadata(key, value) VALUES (?, ?)",
                (key, value),
            )
        # User-editable fields are initialized without imposing an organization name.
        defaults = {
            "workspace_name": self.path.stem,
            "organization_name": "",
            "workspace_description": "",
        }
        for key, value in defaults.items():
            connection.execute(
                "INSERT OR IGNORE INTO app_metadata(key, value) VALUES (?, ?)",
                (key, value),
            )

    @staticmethod
    def _initialize_service_formats(connection: sqlite3.Connection) -> None:
        """Keep a newly created Atlas database operationally empty.

        Existing databases retain any service formats they already contain; this
        initializer deliberately does not seed sample/operational records.
        """
        return

    @staticmethod
    def _ensure_column(
        connection: sqlite3.Connection,
        table: str,
        column: str,
        declaration: str,
    ) -> None:
        existing = {
            str(row[1]).lower()
            for row in connection.execute(f'PRAGMA table_info("{table}")')
        }
        if column.lower() not in existing:
            connection.execute(
                f'ALTER TABLE "{table}" ADD COLUMN "{column}" {declaration}'
            )

    _SYNC_TABLES = (
        "buildings", "locations", "dependencies", "equipment",
        "service_orders", "counter_records",
    )

    def _sync_backup_path(self) -> Path:
        backup_dir = self.path.parent.parent / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        return backup_dir / f"codecafe_atlas_before_sync_identity_{stamp}.db"

    def _needs_sync_migration(self, connection: sqlite3.Connection) -> bool:
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        for table in self._SYNC_TABLES:
            if table not in tables:
                continue
            columns = {
                str(row[1]).lower()
                for row in connection.execute(f'PRAGMA table_info("{table}")')
            }
            if "record_uuid" not in columns:
                return True
        return False

    def _backup_before_sync_migration(self, connection: sqlite3.Connection) -> None:
        if not self.path.exists() or self.path.stat().st_size == 0:
            return
        destination = self._sync_backup_path()
        target = sqlite3.connect(destination)
        try:
            connection.backup(target)
        finally:
            target.close()

    def _installation_uuid(self, connection: sqlite3.Connection) -> str:
        row = connection.execute(
            "SELECT value FROM sync_metadata WHERE key='installation_uuid'"
        ).fetchone()
        if row and str(row[0]).strip():
            return str(row[0]).strip()
        value = str(uuid.uuid4())
        connection.execute(
            "INSERT OR REPLACE INTO sync_metadata(key, value, updated_at) "
            "VALUES ('installation_uuid', ?, CURRENT_TIMESTAMP)",
            (value,),
        )
        return value

    def _prepare_sync_identity(self, connection: sqlite3.Connection) -> None:
        if self._needs_sync_migration(connection):
            self._backup_before_sync_migration(connection)

        installation_uuid = self._installation_uuid(connection)
        for table in self._SYNC_TABLES:
            self._ensure_column(connection, table, "record_uuid", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(connection, table, "created_by_installation", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(connection, table, "updated_by_installation", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(connection, table, "revision", "INTEGER NOT NULL DEFAULT 1")
            self._ensure_column(connection, table, "deleted_at", "TEXT")

            rows = connection.execute(
                f'SELECT id FROM "{table}" WHERE trim(record_uuid) = ""'
            ).fetchall()
            for row in rows:
                record_uuid = ""
                if table == "counter_records":
                    existing_uid = connection.execute(
                        "SELECT record_uid FROM counter_records WHERE id=?",
                        (int(row["id"]),),
                    ).fetchone()
                    record_uuid = str(existing_uid[0] or "").strip() if existing_uid else ""
                record_uuid = record_uuid or str(uuid.uuid4())
                connection.execute(
                    f'''UPDATE "{table}"
                        SET record_uuid=?,
                            created_by_installation=CASE WHEN trim(created_by_installation)='' THEN ? ELSE created_by_installation END,
                            updated_by_installation=CASE WHEN trim(updated_by_installation)='' THEN ? ELSE updated_by_installation END,
                            revision=CASE WHEN revision IS NULL OR revision < 1 THEN 1 ELSE revision END
                        WHERE id=?''',
                    (record_uuid, installation_uuid, installation_uuid, int(row["id"])),
                )

            connection.execute(
                f'CREATE UNIQUE INDEX IF NOT EXISTS idx_{table}_record_uuid ON "{table}"(record_uuid)'
            )
            self._install_sync_triggers(connection, table, installation_uuid)

        connection.execute(
            "INSERT OR REPLACE INTO sync_metadata(key, value, updated_at) "
            "VALUES ('sync_schema_version', '1', CURRENT_TIMESTAMP)"
        )

    @staticmethod
    def _install_sync_triggers(
        connection: sqlite3.Connection, table: str, installation_uuid: str
    ) -> None:
        safe_installation = installation_uuid.replace("'", "''")
        insert_trigger = f"trg_{table}_sync_insert"
        update_trigger = f"trg_{table}_sync_update"
        connection.execute(f'DROP TRIGGER IF EXISTS "{insert_trigger}"')
        connection.execute(f'DROP TRIGGER IF EXISTS "{update_trigger}"')
        connection.executescript(
            f'''CREATE TRIGGER "{insert_trigger}"
            AFTER INSERT ON "{table}"
            WHEN trim(NEW.record_uuid) = ''
            BEGIN
                UPDATE "{table}"
                SET record_uuid = lower(hex(randomblob(4))) || '-' ||
                                  lower(hex(randomblob(2))) || '-4' ||
                                  substr(lower(hex(randomblob(2))), 2) || '-' ||
                                  substr('89ab', abs(random()) % 4 + 1, 1) ||
                                  substr(lower(hex(randomblob(2))), 2) || '-' ||
                                  lower(hex(randomblob(6))),
                    created_by_installation = '{safe_installation}',
                    updated_by_installation = '{safe_installation}',
                    revision = 1
                WHERE id = NEW.id;
            END;

            CREATE TRIGGER "{update_trigger}"
            AFTER UPDATE ON "{table}"
            WHEN OLD.record_uuid <> '' AND NEW.revision = OLD.revision
            BEGIN
                UPDATE "{table}"
                SET updated_at = CURRENT_TIMESTAMP,
                    updated_by_installation = '{safe_installation}',
                    revision = OLD.revision + 1
                WHERE id = NEW.id;
            END;'''
        )

    def sync_identity_status(self) -> dict[str, Any]:
        with self.connect() as connection:
            installation_uuid = self._installation_uuid(connection)
            tables: dict[str, dict[str, int]] = {}
            for table in self._SYNC_TABLES:
                total = int(connection.execute(
                    f'SELECT COUNT(*) FROM "{table}"'
                ).fetchone()[0])
                identified = int(connection.execute(
                    f'SELECT COUNT(*) FROM "{table}" WHERE trim(record_uuid) <> ""'
                ).fetchone()[0])
                tables[table] = {"total": total, "identified": identified}
            return {
                "installation_uuid": installation_uuid,
                "sync_schema_version": "1",
                "tables": tables,
            }

    @staticmethod
    def _compose_location_address(row: sqlite3.Row) -> str:
        street_number = " ".join(
            part for part in (
                str(row["street"] or "").strip(),
                str(row["exterior_number"] or "").strip(),
            ) if part
        )
        parts = [
            street_number,
            str(row["colony"] or "").strip(),
            f'C.P. {row["postal_code"]}' if row["postal_code"] else "",
            str(row["city"] or "").strip(),
            str(row["state"] or "").strip(),
        ]
        return ", ".join(part for part in parts if part)

    def _synchronize_buildings(self, connection: sqlite3.Connection) -> None:
        """Create one canonical building record and link every location to it.

        Existing modules continue reading locations.building, while the Directory
        uses buildings.name/address as the single editable source of truth.
        """
        rows = connection.execute(
            """
            SELECT id, building, city, state, street, exterior_number,
                   colony, postal_code, floor, building_id
            FROM locations
            ORDER BY id
            """
        ).fetchall()
        for row in rows:
            name = str(row["building"] or "").strip() or "Edificio no especificado"
            address = self._compose_location_address(row)
            building = connection.execute(
                "SELECT id, address FROM buildings WHERE name = ? COLLATE NOCASE",
                (name,),
            ).fetchone()
            if building is None:
                cursor = connection.execute(
                    "INSERT INTO buildings(name, address) VALUES (?, ?)",
                    (name, address),
                )
                building_id = int(cursor.lastrowid)
            else:
                building_id = int(building["id"])
                if not str(building["address"] or "").strip() and address:
                    connection.execute(
                        "UPDATE buildings SET address=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                        (address, building_id),
                    )
            if row["building_id"] != building_id:
                connection.execute(
                    "UPDATE locations SET building_id=? WHERE id=?",
                    (building_id, int(row["id"])),
                )

    def list_buildings(self) -> list[sqlite3.Row]:
        """Return canonical buildings with their detailed address fields."""
        with self.connect() as connection:
            return list(connection.execute(
                """
                SELECT b.id,b.name,b.street,b.exterior_number,b.colony,b.city,b.state,
                       b.postal_code,b.country,b.notes,
                       trim(b.street ||
                           CASE WHEN trim(b.exterior_number)<>'' THEN ' '||b.exterior_number ELSE '' END ||
                           CASE WHEN trim(b.colony)<>'' THEN ', '||b.colony ELSE '' END ||
                           CASE WHEN trim(b.city)<>'' THEN ', '||b.city ELSE '' END ||
                           CASE WHEN trim(b.state)<>'' THEN ', '||b.state ELSE '' END ||
                           CASE WHEN trim(b.postal_code)<>'' THEN ' C.P. '||b.postal_code ELSE '' END ||
                           CASE WHEN trim(b.country)<>'' THEN ', '||b.country ELSE '' END) AS address,
                       COUNT(DISTINCT d.id) AS dependency_count,
                       COUNT(DISTINCT e.id) AS equipment_count
                FROM atlas_buildings b
                LEFT JOIN atlas_dependencies d ON d.building_id=b.id AND d.active=1
                LEFT JOIN atlas_equipment e ON e.dependency_id=d.id
                GROUP BY b.id
                ORDER BY b.name COLLATE NOCASE
                """
            ).fetchall())

    def get_building(self, building_id: int) -> sqlite3.Row | None:
        with self.connect() as connection:
            return connection.execute(
                """SELECT id,name,street,exterior_number,colony,city,state,
                          postal_code,country,notes
                   FROM atlas_buildings WHERE id=?""",
                (building_id,),
            ).fetchone()

    def _find_or_create_building(
        self,
        connection: sqlite3.Connection,
        name: str,
        address: str = "",
    ) -> int:
        name = str(name or "").strip() or "Edificio no especificado"
        address = str(address or "").strip()
        row = connection.execute(
            "SELECT id, address FROM buildings WHERE name=? COLLATE NOCASE",
            (name,),
        ).fetchone()
        if row is not None:
            building_id = int(row["id"])
            if not str(row["address"] or "").strip() and address:
                connection.execute(
                    "UPDATE buildings SET address=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (address, building_id),
                )
            return building_id
        cursor = connection.execute(
            "INSERT INTO buildings(name, address) VALUES (?, ?)",
            (name, address),
        )
        return int(cursor.lastrowid)

    @staticmethod
    def _normalize_organizational_name(value: Any) -> str:
        """Canonicalize organization labels for duplicate and similarity checks."""
        text = unicodedata.normalize("NFKD", str(value or "").casefold())
        text = "".join(ch for ch in text if not unicodedata.combining(ch))
        number_words = {
            "primero": "1", "primer": "1", "primera": "1", "uno": "1",
            "segundo": "2", "segunda": "2", "dos": "2",
            "tercero": "3", "tercer": "3", "tercera": "3", "tres": "3",
            "cuarto": "4", "cuarta": "4", "cuatro": "4",
            "quinto": "5", "quinta": "5", "cinco": "5",
            "sexto": "6", "sexta": "6", "seis": "6",
            "septimo": "7", "septima": "7", "siete": "7",
            "octavo": "8", "octava": "8", "ocho": "8",
            "noveno": "9", "novena": "9", "nueve": "9",
            "decimo": "10", "decima": "10", "diez": "10",
            "undecimo": "11", "undecima": "11", "once": "11",
            "duodecimo": "12", "duodecima": "12", "doce": "12",
        }
        tokens = re.findall(r"[a-z0-9]+", text)
        normalized = [number_words.get(token, token) for token in tokens]
        return " ".join(normalized)

    @classmethod
    def _organizational_similarity(cls, left: Any, right: Any) -> float:
        """Similarity score robust to punctuation, word order and common numbering styles."""
        a = cls._normalize_organizational_name(left)
        b = cls._normalize_organizational_name(right)
        if not a or not b:
            return 0.0
        if a == b:
            return 1.0
        ta, tb = a.split(), b.split()
        sa, sb = " ".join(sorted(ta)), " ".join(sorted(tb))
        sequence = max(SequenceMatcher(None, a, b).ratio(), SequenceMatcher(None, sa, sb).ratio())
        aset, bset = set(ta), set(tb)
        jaccard = len(aset & bset) / max(1, len(aset | bset))
        containment = len(aset & bset) / max(1, min(len(aset), len(bset)))
        return max(sequence, jaccard, containment * 0.96)

    def similar_buildings(self, name: str, exclude_id: int | None = None) -> list[dict[str, Any]]:
        incoming = self._normalize_organizational_name(name)
        if not incoming:
            return []
        with self.connect() as connection:
            rows = connection.execute("SELECT id,name FROM atlas_buildings ORDER BY name COLLATE NOCASE").fetchall()
        result = []
        for row in rows:
            if exclude_id is not None and int(row["id"]) == int(exclude_id):
                continue
            score = self._organizational_similarity(name, row["name"])
            if score >= 0.80:
                result.append({"id": int(row["id"]), "name": str(row["name"]), "score": score})
        return sorted(result, key=lambda item: (-item["score"], item["name"].casefold()))

    def similar_dependencies(
        self, building_name: str, name: str, *, floor: str = "", exclude_id: int | None = None
    ) -> list[dict[str, Any]]:
        incoming = self._normalize_organizational_name(name)
        if not incoming:
            return []
        with self.connect() as connection:
            rows = connection.execute(
                """SELECT d.id,d.name,d.floor,b.name AS building
                   FROM atlas_dependencies d JOIN atlas_buildings b ON b.id=d.building_id
                   WHERE b.name=? COLLATE NOCASE AND d.active=1
                   ORDER BY d.name COLLATE NOCASE""",
                (str(building_name or "").strip(),),
            ).fetchall()
        result = []
        for row in rows:
            if exclude_id is not None and int(row["id"]) == int(exclude_id):
                continue
            score = self._organizational_similarity(name, row["name"])
            if score >= 0.80:
                result.append({
                    "id": int(row["id"]), "name": str(row["name"]),
                    "floor": str(row["floor"] or ""), "building": str(row["building"] or ""), "score": score,
                })
        return sorted(result, key=lambda item: (-item["score"], item["name"].casefold()))

    def save_building(self, values: dict[str, Any], building_id: int | None = None) -> int:
        """Save the single authoritative detailed address for a building."""
        name=str(values.get("name") or "").strip()
        if not name:
            raise ValueError("Escribe el nombre del edificio.")
        keys=("street","exterior_number","colony","city","state","postal_code","country","notes")
        data={k:str(values.get(k,"") or "").strip() for k in keys}
        data["country"]=data["country"] or "México"
        params=(name,data["street"],data["exterior_number"],data["colony"],data["city"],data["state"],data["postal_code"],data["country"],data["notes"])
        with self.connect() as connection:
            duplicate_rows=connection.execute("SELECT id,name FROM atlas_buildings").fetchall()
            incoming_key=self._normalize_organizational_name(name)
            for duplicate in duplicate_rows:
                if building_id is not None and int(duplicate["id"]) == int(building_id):
                    continue
                if self._normalize_organizational_name(duplicate["name"]) == incoming_key:
                    raise ValueError(f"Ya existe un edificio equivalente: {duplicate['name']}.")
            if building_id is None:
                cursor=connection.execute("""INSERT INTO atlas_buildings
                    (name,street,exterior_number,colony,city,state,postal_code,country,notes)
                    VALUES(?,?,?,?,?,?,?,?,?)""",params)
                return int(cursor.lastrowid)
            if connection.execute("SELECT 1 FROM atlas_buildings WHERE id=?",(building_id,)).fetchone() is None:
                raise ValueError("El edificio ya no existe.")
            connection.execute("""UPDATE atlas_buildings SET name=?,street=?,exterior_number=?,colony=?,city=?,state=?,
                postal_code=?,country=?,notes=?,updated_at=CURRENT_TIMESTAMP WHERE id=?""",params+(building_id,))
            return int(building_id)

    def directory_equipment(self) -> dict[int, list[sqlite3.Row]]:
        """Return each canonical equipment record exactly once, grouped by dependency.

        Directory and Inventory are two views of the same ``atlas_equipment``
        table.  Do not use the legacy ``equipment`` compatibility view here:
        synchronization/relationship compatibility rows can multiply JOIN
        cardinality and make Directory report more equipment than Inventory.
        """
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT e.id, e.dependency_id, e.equipment_type, e.brand, e.model,
                       e.serial_number, e.inventory_number, e.ip_address,
                       e.hostname, e.status,
                       (
                           SELECT cr.total_prints
                           FROM atlas_counter_readings cr
                           WHERE cr.equipment_id=e.id
                              OR (cr.equipment_id IS NULL
                                  AND cr.serial_snapshot<>''
                                  AND lower(replace(replace(replace(cr.serial_snapshot, '-', ''), ' ', ''), '.', ''))
                                      = lower(replace(replace(replace(e.serial_number, '-', ''), ' ', ''), '.', '')))
                           ORDER BY
                               CASE WHEN cr.reading_date='' THEN 1 ELSE 0 END,
                               cr.reading_date DESC, cr.id DESC
                           LIMIT 1
                       ) AS latest_counter,
                       (
                           SELECT cr.reading_date
                           FROM atlas_counter_readings cr
                           WHERE cr.equipment_id=e.id
                              OR (cr.equipment_id IS NULL
                                  AND cr.serial_snapshot<>''
                                  AND lower(replace(replace(replace(cr.serial_snapshot, '-', ''), ' ', ''), '.', ''))
                                      = lower(replace(replace(replace(e.serial_number, '-', ''), ' ', ''), '.', '')))
                           ORDER BY
                               CASE WHEN cr.reading_date='' THEN 1 ELSE 0 END,
                               cr.reading_date DESC, cr.id DESC
                           LIMIT 1
                       ) AS latest_counter_date
                FROM atlas_equipment e
                ORDER BY e.dependency_id, e.equipment_type COLLATE NOCASE,
                         e.brand COLLATE NOCASE, e.model COLLATE NOCASE,
                         e.serial_number COLLATE NOCASE, e.id
                """
            ).fetchall()
        result: dict[int, list[sqlite3.Row]] = {}
        for row in rows:
            result.setdefault(int(row["dependency_id"]), []).append(row)
        return result

    def list_equipment_counter_records(self, equipment_id: int) -> list[sqlite3.Row]:
        """Return all readings linked to an equipment record, newest first."""
        equipment = self.get_equipment_detailed(equipment_id)
        if equipment is None:
            return []
        serial = self._normalize_equipment_identifier(equipment["serial_number"])
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, record_uid, equipment_id, reading_date, serial_number,
                       model, source_file, total_prints, office_prints,
                       letter_prints, duplex_sheets, jam_events,
                       misfeed_events, economode_prints, format_type,
                       created_at, updated_at
                FROM counter_records
                WHERE equipment_id=?
                   OR (
                        equipment_id IS NULL AND ?<>'' AND serial_number<>''
                        AND lower(replace(replace(replace(serial_number, '-', ''), ' ', ''), '.', ''))=?
                   )
                ORDER BY CASE WHEN reading_date='' THEN 1 ELSE 0 END,
                         reading_date DESC, id DESC
                """,
                (equipment_id, serial, serial),
            ).fetchall()
        return list(rows)

    def save_equipment_counter(
        self,
        equipment_id: int,
        values: dict[str, Any],
        record_uid: str | None = None,
    ) -> str:
        """Insert or update one counter reading in the existing counter fields."""
        with self.connect() as connection:
            equipment = connection.execute(
                "SELECT id, serial_number, model FROM equipment WHERE id=?",
                (equipment_id,),
            ).fetchone()
            if equipment is None:
                raise ValueError("El equipo ya no existe.")

            total = self._counter_number(values.get("total_prints"))
            letter = self._counter_number(values.get("letter_prints"))
            if letter is None:
                letter = self._counter_number(values.get("office_prints"))
            equivalent = None
            duplex = self._counter_number(values.get("duplex_sheets"))
            jams = self._counter_number(values.get("jam_events"))
            misfeeds = self._counter_number(values.get("misfeed_events"))
            economode = self._counter_number(values.get("economode_prints"))
            if total is None:
                raise ValueError("Escribe el total de impresiones.")

            reading_date = str(values.get("reading_date") or "").strip()
            if not reading_date:
                raise ValueError("Escribe la fecha de la lectura.")

            uid = str(record_uid or "").strip() or str(uuid.uuid4())
            existing = connection.execute(
                "SELECT source_file, format_type FROM counter_records WHERE record_uid=?",
                (uid,),
            ).fetchone()
            source_file = str(existing["source_file"] or "") if existing else ""
            format_type = (
                str(existing["format_type"] or "")
                if existing else "Registro manual desde Directorio"
            )
            connection.execute(
                """
                INSERT INTO counter_records (
                    record_uid, equipment_id, reading_date, serial_number,
                    model, source_file, total_prints, office_prints,
                    letter_prints, duplex_sheets, jam_events,
                    misfeed_events, economode_prints, format_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(record_uid) DO UPDATE SET
                    equipment_id=excluded.equipment_id,
                    reading_date=excluded.reading_date,
                    serial_number=excluded.serial_number,
                    model=excluded.model,
                    total_prints=excluded.total_prints,
                    office_prints=excluded.office_prints,
                    letter_prints=excluded.letter_prints,
                    duplex_sheets=excluded.duplex_sheets,
                    jam_events=excluded.jam_events,
                    misfeed_events=excluded.misfeed_events,
                    economode_prints=excluded.economode_prints,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (
                    uid, equipment_id, reading_date,
                    str(equipment["serial_number"] or ""),
                    str(equipment["model"] or ""),
                    source_file, total, equivalent, letter,
                    duplex, jams, misfeeds, economode, format_type,
                ),
            )
            return uid

    def database_health(self) -> dict[str, Any]:
        with self.connect() as connection:
            integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
            foreign_keys = [tuple(row) for row in connection.execute("PRAGMA foreign_key_check")]
            counts = {
                table: int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
                for table in ("buildings", "locations", "dependencies", "equipment", "counter_records", "service_orders")
            }
            connection.execute("ANALYZE")
            connection.execute("PRAGMA optimize")
        return {"integrity": integrity, "foreign_key_errors": foreign_keys, "counts": counts}

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _connect_readonly(path: Path) -> sqlite3.Connection:
        connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _tables(connection: sqlite3.Connection) -> set[str]:
        return {
            str(row[0]).lower()
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }

    @staticmethod
    def _columns(connection: sqlite3.Connection, table: str) -> dict[str, str]:
        return {
            str(row[1]).lower(): str(row[1])
            for row in connection.execute(f'PRAGMA table_info("{table}")')
        }

    @staticmethod
    def _find_table(tables: set[str], candidates: list[str]) -> str | None:
        for candidate in candidates:
            if candidate.lower() in tables:
                return candidate.lower()
        return None

    @staticmethod
    def _pick(row: sqlite3.Row, columns: dict[str, str], *names: str, default: str = "") -> str:
        for name in names:
            real = columns.get(name.lower())
            if real is not None:
                value = row[real]
                if value is not None:
                    return str(value).strip()
        return default

    def backup(self, backup_dir: Path) -> Path:
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        destination = backup_dir / f"codecafe_atlas_{stamp}.db"
        sequence = 1
        while destination.exists():
            destination = backup_dir / f"codecafe_atlas_{stamp}_{sequence:02d}.db"
            sequence += 1
        if self.path.exists():
            source = sqlite3.connect(self.path)
            target = sqlite3.connect(destination)
            try:
                source.backup(target)
            finally:
                target.close()
                source.close()
        else:
            sqlite3.connect(destination).close()
        return destination

    def inspect_database(self, source_path: Path) -> dict[str, Any]:
        source_path = Path(source_path)
        if not source_path.exists():
            raise FileNotFoundError("La base seleccionada no existe.")

        try:
            connection = self._connect_readonly(source_path)
        except sqlite3.Error as error:
            raise ValueError(f"El archivo no parece ser una base SQLite válida: {error}") from error

        try:
            result = connection.execute("PRAGMA integrity_check").fetchone()
            if not result or str(result[0]).lower() != "ok":
                raise ValueError(f"La base no pasó la verificación de integridad: {result[0] if result else 'sin respuesta'}")

            tables = self._tables(connection)
            counts = {}
            for table in tables:
                try:
                    counts[table] = int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
                except sqlite3.Error:
                    counts[table] = 0

            # Native Atlas databases may use either the historical storage tables
            # or the normalized clean schema. Compatibility views are intentionally
            # excluded by _tables(), so clean databases must be recognized by their
            # authoritative atlas_* tables rather than by the legacy view names.
            legacy_native = {"locations", "dependencies", "equipment"}.issubset(tables)
            clean_native = {
                "atlas_buildings",
                "atlas_dependencies",
                "atlas_equipment",
            }.issubset(tables)
            native = legacy_native or clean_native
            native_schema = (
                "clean" if clean_native else "legacy-compatible" if legacy_native else ""
            )

            legacy_locations = self._find_table(
                tables, ["ubicaciones", "ubicacion", "locations", "location", "dependencias", "dependencies"]
            )
            legacy_equipment = self._find_table(
                tables, ["equipos", "equipo", "equipment", "inventario", "inventory"]
            )

            if native:
                mode = "native"
            elif legacy_locations or legacy_equipment:
                mode = "legacy"
            else:
                mode = "unsupported"

            return {
                "mode": mode,
                "tables": sorted(tables),
                "counts": counts,
                "location_table": legacy_locations,
                "equipment_table": legacy_equipment,
                "native_schema": native_schema,
            }
        finally:
            connection.close()

    def import_existing_database(self, source_path: Path, backup_dir: Path) -> dict[str, Any]:
        source_path = Path(source_path).resolve()
        if source_path == self.path.resolve():
            raise ValueError("La base seleccionada ya es la base que está usando la aplicación.")

        info = self.inspect_database(source_path)
        if info["mode"] == "unsupported":
            names = ", ".join(info["tables"]) or "ninguna"
            raise ValueError(
                "No se reconoció una estructura compatible.\n\n"
                f"Tablas encontradas: {names}"
            )

        backup_path = self.backup(backup_dir)

        if info["mode"] == "native":
            shutil.copy2(source_path, self.path)
            self.initialize()
            with self.connect() as connection:
                dependency_count = int(connection.execute("SELECT COUNT(*) FROM dependencies").fetchone()[0])
                equipment_count = int(connection.execute("SELECT COUNT(*) FROM equipment").fetchone()[0])
                counter_count = int(connection.execute("SELECT COUNT(*) FROM counter_records").fetchone()[0])
            return {
                "mode": "native",
                "backup": backup_path,
                "dependencies": dependency_count,
                "equipment": equipment_count,
                "counters": counter_count,
                "skipped": 0,
            }

        return self._migrate_legacy(source_path, backup_path)


    @staticmethod
    def _normalized_serial(value: Any) -> str:
        return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())

    def import_preview(self, source_path: Path, *, skip_duplicate_serials: bool = True, skip_blank_serials: bool = False) -> dict[str, Any]:
        info = self.inspect_database(source_path)
        if info["mode"] == "unsupported":
            raise ValueError("La base seleccionada no tiene una estructura compatible.")
        connection = self._connect_readonly(Path(source_path))
        try:
            tables = self._tables(connection)
            if "atlas_equipment" in tables:
                rows = connection.execute("SELECT id, serial_number FROM atlas_equipment ORDER BY id").fetchall()
            else:
                table = info.get("equipment_table")
                if not table:
                    rows = []
                else:
                    columns = self._columns(connection, table)
                    serial_col = self._find_column(columns, ["serial_number", "serie", "serial", "numero_serie", "número_de_serie"])
                    id_col = self._find_column(columns, ["id", "equipment_id", "equipo_id"])
                    if serial_col:
                        rows = connection.execute(f'SELECT {id_col or "rowid"} AS id, "{serial_col}" AS serial_number FROM "{table}" ORDER BY 1').fetchall()
                    else:
                        rows = []
            seen: dict[str, int] = {}
            duplicate_ids: list[int] = []
            blank_ids: list[int] = []
            duplicate_groups: dict[str, list[int]] = {}
            for row in rows:
                rid=int(row[0]); norm=self._normalized_serial(row[1])
                if not norm:
                    blank_ids.append(rid)
                    continue
                if norm in seen:
                    duplicate_ids.append(rid)
                    duplicate_groups.setdefault(norm, [seen[norm]]).append(rid)
                else:
                    seen[norm]=rid
            excluded=set()
            if skip_duplicate_serials: excluded.update(duplicate_ids)
            if skip_blank_serials: excluded.update(blank_ids)
            return {
                "info": info, "equipment_source": len(rows),
                "duplicate_records": len(duplicate_ids), "duplicate_groups": len(duplicate_groups),
                "blank_serials": len(blank_ids), "equipment_after_filter": len(rows)-len(excluded),
                "duplicate_ids": duplicate_ids, "blank_ids": blank_ids,
            }
        finally:
            connection.close()

    def replace_with_filtered_database(self, source_path: Path, backup_dir: Path, *, skip_duplicate_serials: bool = True, skip_blank_serials: bool = False) -> dict[str, Any]:
        source_path=Path(source_path).resolve()
        preview=self.import_preview(source_path, skip_duplicate_serials=skip_duplicate_serials, skip_blank_serials=skip_blank_serials)
        if preview["info"]["mode"] != "native":
            return self.import_existing_database(source_path, backup_dir)
        backup_path=self.backup(backup_dir)
        temp=self.path.with_name(self.path.stem+".importing"+self.path.suffix)
        if temp.exists(): temp.unlink()
        shutil.copy2(source_path, temp)
        try:
            ensure_clean_database(temp)
            with sqlite3.connect(temp) as c:
                c.execute("PRAGMA foreign_keys=ON")
                ids=[]
                if skip_duplicate_serials: ids.extend(preview["duplicate_ids"])
                if skip_blank_serials: ids.extend(preview["blank_ids"])
                ids=sorted(set(ids))
                if ids:
                    marks=','.join('?' for _ in ids)
                    c.execute(f"UPDATE atlas_counter_readings SET equipment_id=NULL WHERE equipment_id IN ({marks})", ids)
                    c.execute(f"UPDATE atlas_service_orders SET equipment_id=NULL WHERE equipment_id IN ({marks})", ids)
                    c.execute(f"DELETE FROM atlas_equipment WHERE id IN ({marks})", ids)
                integrity=c.execute("PRAGMA integrity_check").fetchone()[0]
                fk=list(c.execute("PRAGMA foreign_key_check"))
                if str(integrity).lower()!='ok' or fk:
                    raise ValueError(f"La base filtrada no pasó validación: {integrity}; FK={len(fk)}")
            shutil.move(temp, self.path)
            self.initialize()
        except Exception:
            if temp.exists(): temp.unlink()
            shutil.copy2(backup_path, self.path)
            self.initialize()
            raise
        with self.connect() as c:
            return {
                "mode":"replace-filtered", "backup":backup_path,
                "dependencies":int(c.execute("SELECT COUNT(*) FROM dependencies").fetchone()[0]),
                "equipment":int(c.execute("SELECT COUNT(*) FROM equipment").fetchone()[0]),
                "counters":int(c.execute("SELECT COUNT(*) FROM counter_records").fetchone()[0]),
                "skipped":preview["equipment_source"]-preview["equipment_after_filter"],
                "duplicate_records":preview["duplicate_records"], "blank_serials":preview["blank_serials"],
            }

    def reset_to_empty(self, backup_dir: Path) -> Path:
        backup_path=self.backup(backup_dir)
        temp=self.path.with_name(self.path.stem+".empty"+self.path.suffix)
        if temp.exists(): temp.unlink()
        ensure_clean_database(temp)
        with sqlite3.connect(temp) as c:
            if str(c.execute("PRAGMA integrity_check").fetchone()[0]).lower() != "ok":
                raise ValueError("No se pudo crear una base vacía íntegra.")
        shutil.move(temp, self.path)
        self.initialize()
        return backup_path

    def _migrate_legacy(self, source_path: Path, backup_path: Path) -> dict[str, Any]:
        source = self._connect_readonly(source_path)
        imported_dependencies = 0
        imported_equipment = 0
        skipped = 0

        try:
            tables = self._tables(source)
            location_table = self._find_table(
                tables, ["ubicaciones", "ubicacion", "locations", "location", "dependencias", "dependencies"]
            )
            equipment_table = self._find_table(
                tables, ["equipos", "equipo", "equipment", "inventario", "inventory"]
            )

            location_map: dict[str, int] = {}
            source_location_id_map: dict[str, int] = {}

            with self.connect() as target:
                # Keep current records, importing only additional data.
                if location_table:
                    columns = self._columns(source, location_table)
                    rows = source.execute(f'SELECT * FROM "{location_table}"').fetchall()

                    for index, row in enumerate(rows, start=1):
                        source_id = self._pick(row, columns, "id", "ubicacion_id", "location_id", default=str(index))
                        building = self._pick(row, columns, "edificio", "building")
                        floor = self._pick(row, columns, "piso", "floor")
                        city = self._pick(row, columns, "ciudad", "city")
                        state = self._pick(row, columns, "estado", "state")
                        street = self._pick(row, columns, "calle", "street")
                        # Las bases anteriores guardan la dirección completa en
                        # la columna `direccion`, no en campos separados.
                        # Cuando no existe una calle separada, se conserva el
                        # domicilio completo en `street` para que aparezca bajo
                        # el nombre del edificio sin alterar la base original.
                        full_address = self._pick(
                            row, columns,
                            "direccion", "dirección", "address", "domicilio",
                        )
                        if not street and full_address:
                            street = full_address
                        exterior_number = self._pick(row, columns, "numero", "número", "exterior_number")
                        colony = self._pick(row, columns, "colonia", "colony")
                        postal_code = self._pick(row, columns, "cp", "codigo_postal", "código_postal", "postal_code")
                        court = self._pick(row, columns, "juzgado", "court")
                        tribunal = self._pick(row, columns, "tribunal")
                        office = self._pick(row, columns, "oficina", "office")
                        cta = self._pick(row, columns, "cta", "encargado", "responsable")
                        phone = self._pick(row, columns, "telefono", "teléfono", "phone")
                        email = self._pick(row, columns, "correo", "email")
                        notes = self._pick(row, columns, "observaciones", "notas", "notes")
                        name = self._pick(
                            row, columns,
                            "dependencia", "nombre", "name", "juzgado", "tribunal", "oficina",
                            default=f"Dependencia importada {index}"
                        )

                        identity = "|".join([
                            name.lower(), building.lower(), floor.lower(),
                            office.lower(), court.lower(), tribunal.lower()
                        ])
                        if identity in location_map:
                            dependency_id = location_map[identity]
                        else:
                            location_cursor = target.execute(
                                """
                                INSERT INTO locations
                                (building, city, state, street, exterior_number, colony, postal_code, floor)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                                """,
                                (building, city, state, street, exterior_number, colony, postal_code, floor),
                            )
                            location_id = int(location_cursor.lastrowid)
                            dependency_cursor = target.execute(
                                """
                                INSERT INTO dependencies
                                (location_id, name, court, tribunal, office, cta, phone, email, notes)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                                """,
                                (location_id, name, court, tribunal, office, cta, phone, email, notes),
                            )
                            dependency_id = int(dependency_cursor.lastrowid)
                            location_map[identity] = dependency_id
                            imported_dependencies += 1

                        source_location_id_map[source_id] = dependency_id

                # If no location table exists, create one fallback dependency.
                fallback_dependency_id = None
                if equipment_table and not source_location_id_map:
                    location_cursor = target.execute(
                        "INSERT INTO locations (building) VALUES (?)",
                        ("Ubicación importada",),
                    )
                    fallback_location_id = int(location_cursor.lastrowid)
                    dependency_cursor = target.execute(
                        "INSERT INTO dependencies (location_id, name, notes) VALUES (?, ?, ?)",
                        (
                            fallback_location_id,
                            "Equipos importados sin dependencia",
                            "Creada automáticamente durante la importación."
                        ),
                    )
                    fallback_dependency_id = int(dependency_cursor.lastrowid)
                    imported_dependencies += 1

                if equipment_table:
                    columns = self._columns(source, equipment_table)
                    rows = source.execute(f'SELECT * FROM "{equipment_table}"').fetchall()

                    for row in rows:
                        source_location_id = self._pick(
                            row, columns,
                            "ubicacion_id", "location_id", "dependencia_id", "dependency_id"
                        )
                        dependency_id = source_location_id_map.get(source_location_id, fallback_dependency_id)

                        # Try a textual dependency match when no numeric relation is available.
                        if dependency_id is None:
                            dependency_text = self._pick(
                                row, columns, "dependencia", "ubicacion", "location", "oficina"
                            ).lower()
                            if dependency_text:
                                for identity, candidate_id in location_map.items():
                                    if dependency_text in identity:
                                        dependency_id = candidate_id
                                        break

                        if dependency_id is None:
                            skipped += 1
                            continue

                        equipment_type = self._pick(
                            row, columns, "equipo", "tipo_equipo", "equipment_type", "tipo", "type"
                        )
                        brand = self._pick(row, columns, "marca", "brand")
                        model = self._pick(row, columns, "modelo", "model")
                        serial_number = self._pick(
                            row, columns, "numero_serie", "número_serie", "serie", "serial_number", "serial"
                        )
                        inventory_number = self._pick(
                            row, columns, "numero_inventario", "número_inventario", "inventario",
                            "inventory_number", "asset_number", "numero_activo"
                        )
                        ip_address = self._pick(row, columns, "ip", "ip_address", "direccion_ip")
                        hostname = self._pick(row, columns, "hostname", "host", "nombre_host")
                        status = self._pick(row, columns, "estado", "status", default="Activo") or "Activo"
                        notes = self._pick(row, columns, "observaciones", "notas", "notes")

                        # Avoid duplicate serials when available.
                        if serial_number:
                            duplicate = target.execute(
                                "SELECT 1 FROM equipment WHERE serial_number = ? LIMIT 1",
                                (serial_number,),
                            ).fetchone()
                            if duplicate:
                                skipped += 1
                                continue

                        target.execute(
                            """
                            INSERT INTO equipment
                            (dependency_id, equipment_type, brand, model, serial_number,
                             inventory_number, ip_address, hostname, status, notes)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                dependency_id, equipment_type, brand, model, serial_number,
                                inventory_number, ip_address, hostname, status, notes,
                            ),
                        )
                        imported_equipment += 1

            self.initialize()
            return {
                "mode": "legacy",
                "backup": backup_path,
                "dependencies": imported_dependencies,
                "equipment": imported_equipment,
                "counters": 0,
                "skipped": skipped,
            }
        except Exception:
            # Restore the exact previous database when migration fails.
            shutil.copy2(backup_path, self.path)
            self.initialize()
            raise
        finally:
            source.close()

    def list_dependencies(self, search: str = "") -> list[sqlite3.Row]:
        """Return one row per canonical dependency.

        Office and CTA are display attributes selected deterministically from
        their normalized relationship tables.  Correlated subqueries prevent
        multiple CTA/office rows from duplicating a dependency in Directory.
        """
        pattern = f"%{search.strip()}%"
        query = """
            SELECT
                d.id, d.id AS location_id, d.name, d.court, d.tribunal,
                COALESCE((SELECT o.name FROM atlas_offices o
                          WHERE o.dependency_id=d.id ORDER BY o.id LIMIT 1), '') AS office,
                COALESCE((SELECT p.full_name
                          FROM atlas_dependency_people dp
                          JOIN atlas_people p ON p.id=dp.person_id
                          WHERE dp.dependency_id=d.id AND lower(dp.role)='cta'
                          ORDER BY dp.person_id LIMIT 1), '') AS cta,
                d.phone, d.email, d.notes, b.id AS building_id, b.name AS building,
                trim(b.street ||
                     CASE WHEN trim(b.exterior_number)<>'' THEN ' '||b.exterior_number ELSE '' END ||
                     CASE WHEN trim(b.colony)<>'' THEN ', '||b.colony ELSE '' END ||
                     CASE WHEN trim(b.city)<>'' THEN ', '||b.city ELSE '' END ||
                     CASE WHEN trim(b.state)<>'' THEN ', '||b.state ELSE '' END ||
                     CASE WHEN trim(b.postal_code)<>'' THEN ' C.P. '||b.postal_code ELSE '' END ||
                     CASE WHEN trim(b.country)<>'' THEN ', '||b.country ELSE '' END) AS building_address,
                b.city, b.state, b.street, b.exterior_number, b.colony, b.postal_code, d.floor
            FROM atlas_dependencies d
            JOIN atlas_buildings b ON b.id=d.building_id
            WHERE d.active=1
              AND (
                ?='%%' OR d.name LIKE ? OR d.court LIKE ? OR d.tribunal LIKE ?
                OR COALESCE((SELECT o.name FROM atlas_offices o WHERE o.dependency_id=d.id ORDER BY o.id LIMIT 1),'') LIKE ?
                OR COALESCE((SELECT p.full_name FROM atlas_dependency_people dp JOIN atlas_people p ON p.id=dp.person_id
                             WHERE dp.dependency_id=d.id AND lower(dp.role)='cta' ORDER BY dp.person_id LIMIT 1),'') LIKE ?
                OR b.name LIKE ?
                OR trim(b.street||' '||b.exterior_number||' '||b.colony||' '||b.city||' '||b.state||' '||b.postal_code) LIKE ?
                OR d.floor LIKE ?
              )
            ORDER BY b.name COLLATE NOCASE, d.floor COLLATE NOCASE, d.name COLLATE NOCASE, d.id
        """
        with self.connect() as connection:
            return list(connection.execute(query, (pattern,) * 9).fetchall())

    def get_dependency(self, dependency_id: int) -> sqlite3.Row | None:
        rows = self.list_dependencies()
        return next((row for row in rows if row["id"] == dependency_id), None)

    def save_dependency(self, values: dict[str, Any], dependency_id: int | None = None) -> int:
        """Save directly to the normalized Atlas schema."""
        with self.connect() as connection:
            building_name = str(values.get("building", "") or "").strip() or "Sin edificio"
            row = connection.execute(
                "SELECT id,name FROM atlas_buildings WHERE name=? COLLATE NOCASE",
                (building_name,),
            ).fetchone()
            if row is None:
                # Never allow a dependency save path to silently create an equivalent
                # building under alternate punctuation, accents, word order or numbering.
                incoming_building_key = " ".join(sorted(self._normalize_organizational_name(building_name).split()))
                for existing_building in connection.execute("SELECT id,name FROM atlas_buildings").fetchall():
                    existing_key = " ".join(sorted(self._normalize_organizational_name(existing_building["name"]).split()))
                    if incoming_building_key and existing_key == incoming_building_key:
                        raise ValueError(
                            f"Ya existe un edificio equivalente: {existing_building['name']}. "
                            "Selecciona el edificio existente en la lista."
                        )
                cursor = connection.execute(
                    """INSERT INTO atlas_buildings
                    (name, city, state, street, exterior_number, colony, postal_code)
                    VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (building_name, values.get("city", ""), values.get("state", ""),
                     values.get("street", ""), values.get("exterior_number", ""),
                     values.get("colony", ""), values.get("postal_code", "")),
                )
                building_id = int(cursor.lastrowid)
            else:
                # Dependencies inherit address from the building.
                building_id = int(row["id"])
            # Block exact/equivalent duplicate dependencies even when punctuation, accents,
            # word order or numbering style differ. Near matches are confirmed by the UI.
            incoming_key = " ".join(sorted(self._normalize_organizational_name(values["name"]).split()))
            existing_dependencies = connection.execute(
                "SELECT id,name FROM atlas_dependencies WHERE building_id=? AND active=1",
                (building_id,),
            ).fetchall()
            for existing in existing_dependencies:
                if dependency_id is not None and int(existing["id"]) == int(dependency_id):
                    continue
                existing_key = " ".join(sorted(self._normalize_organizational_name(existing["name"]).split()))
                if incoming_key and existing_key == incoming_key:
                    raise ValueError(f"Ya existe una dependencia equivalente en este edificio: {existing['name']}.")

            if dependency_id is None:
                cursor = connection.execute(
                    """INSERT INTO atlas_dependencies
                    (building_id,name,court,tribunal,floor,phone,email,notes,active)
                    VALUES(?,?,?,?,?,?,?,?,1)""",
                    (building_id, values["name"], values.get("court", ""), values.get("tribunal", ""),
                     values.get("floor", ""), values.get("phone", ""), values.get("email", ""),
                     values.get("notes", "")),
                )
                dependency_id = int(cursor.lastrowid)
            else:
                connection.execute(
                    """UPDATE atlas_dependencies SET building_id=?,name=?,court=?,tribunal=?,floor=?,
                    phone=?,email=?,notes=?,updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                    (building_id, values["name"], values.get("court", ""), values.get("tribunal", ""),
                     values.get("floor", ""), values.get("phone", ""), values.get("email", ""),
                     values.get("notes", ""), dependency_id),
                )
                connection.execute("DELETE FROM atlas_offices WHERE dependency_id=?", (dependency_id,))
                connection.execute("DELETE FROM atlas_dependency_people WHERE dependency_id=? AND lower(role)='cta'", (dependency_id,))
            office = str(values.get("office", "") or "").strip()
            if office:
                connection.execute("INSERT INTO atlas_offices(dependency_id,name) VALUES(?,?)", (dependency_id, office))
            cta = str(values.get("cta", "") or "").strip()
            if cta:
                connection.execute("INSERT OR IGNORE INTO atlas_people(full_name,phone,email) VALUES(?,?,?)",
                                   (cta, values.get("phone", ""), values.get("email", "")))
                person_id = connection.execute(
                    "SELECT id FROM atlas_people WHERE lower(trim(full_name))=lower(trim(?))", (cta,)
                ).fetchone()[0]
                connection.execute("INSERT INTO atlas_dependency_people(dependency_id,person_id,role) VALUES(?,?,'CTA')",
                                   (dependency_id, person_id))
            return int(dependency_id)

    def update_dependency_city_state(
        self, dependency_id: int, city: str, state: str
    ) -> None:
        """Update the city/state of the location linked to a dependency."""
        with self.connect() as connection:
            row = connection.execute(
                "SELECT location_id FROM dependencies WHERE id = ?",
                (dependency_id,),
            ).fetchone()
            if row is None:
                raise ValueError("La dependencia ya no existe.")
            connection.execute(
                """
                UPDATE locations
                SET city = ?, state = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (str(city or "").strip(), str(state or "").strip(), int(row["location_id"])),
            )

    def delete_dependency(self, dependency_id: int) -> None:
        with self.connect() as connection:
            equipment_count = connection.execute(
                "SELECT COUNT(*) FROM equipment WHERE dependency_id = ?",
                (dependency_id,),
            ).fetchone()[0]
            if equipment_count:
                raise ValueError(
                    "No se puede eliminar porque la dependencia tiene equipos registrados."
                )
            connection.execute("DELETE FROM dependencies WHERE id = ?", (dependency_id,))

    def dependency_choices(self) -> list[sqlite3.Row]:
        with self.connect() as connection:
            return list(connection.execute(
                """
                SELECT d.id, d.name, l.building, l.floor
                FROM dependencies d
                JOIN locations l ON l.id = d.location_id
                WHERE d.active = 1
                ORDER BY l.building COLLATE NOCASE, l.floor COLLATE NOCASE, d.name COLLATE NOCASE
                """
            ).fetchall())

    def list_equipment(self, search: str = "") -> list[sqlite3.Row]:
        """Return one row per canonical equipment record.

        Inventory must never depend on compatibility views for row cardinality;
        imported/legacy synchronization metadata can otherwise multiply one
        equipment row in a JOIN and inflate counts.
        """
        pattern = f"%{search.strip()}%"
        with self.connect() as connection:
            return list(connection.execute(
                """
                SELECT
                    e.id, e.dependency_id, e.equipment_type, e.brand, e.model,
                    e.serial_number, e.inventory_number, e.ip_address, e.hostname, e.status, e.notes,
                    d.name AS dependency_name, b.name AS building, d.floor
                FROM atlas_equipment e
                JOIN atlas_dependencies d ON d.id = e.dependency_id
                JOIN atlas_buildings b ON b.id = d.building_id
                WHERE
                    ? = '%%'
                    OR e.equipment_type LIKE ?
                    OR e.brand LIKE ?
                    OR e.model LIKE ?
                    OR e.serial_number LIKE ?
                    OR e.inventory_number LIKE ?
                    OR e.ip_address LIKE ?
                    OR e.hostname LIKE ?
                    OR e.status LIKE ?
                    OR d.name LIKE ?
                    OR b.name LIKE ?
                ORDER BY d.name COLLATE NOCASE, e.equipment_type COLLATE NOCASE, e.model COLLATE NOCASE, e.id
                """,
                (pattern,) * 11,
            ).fetchall())

    @staticmethod
    def _normalize_equipment_identifier(value: Any) -> str:
        """Normalize serials/inventory numbers/hostnames for duplicate detection."""
        return re.sub(r"[^0-9a-z]+", "", str(value or "").casefold())

    def find_equipment_duplicate(
        self,
        values: dict[str, Any],
        exclude_id: int | None = None,
    ) -> tuple[sqlite3.Row, str] | None:
        identifiers = (
            ("serial_number", "número de serie"),
            ("inventory_number", "número de inventario"),
            ("hostname", "hostname"),
            ("ip_address", "dirección IP"),
        )
        normalized = {
            key: self._normalize_equipment_identifier(values.get(key, ""))
            for key, _label in identifiers
        }
        if not any(normalized.values()):
            return None

        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT e.*, d.name AS dependency_name
                FROM equipment e
                JOIN dependencies d ON d.id = e.dependency_id
                ORDER BY e.id
                """
            ).fetchall()

        for row in rows:
            if exclude_id is not None and int(row["id"]) == int(exclude_id):
                continue
            for key, label in identifiers:
                incoming = normalized[key]
                existing = self._normalize_equipment_identifier(row[key])
                if incoming and existing and incoming == existing:
                    return row, label
        return None

    def get_equipment_detailed(self, equipment_id: int) -> sqlite3.Row | None:
        with self.connect() as connection:
            return connection.execute(
                """
                SELECT
                    e.id, e.dependency_id, e.equipment_type, e.brand, e.model,
                    e.serial_number, e.inventory_number, e.assigned_user, e.ip_address, e.hostname,
                    e.status, e.notes,
                    d.name AS dependency_name, d.office, d.cta, d.phone,
                    d.phone AS dependency_phone, d.email,
                    l.building, l.floor, l.city, l.state, l.street,
                    l.exterior_number, l.colony, l.postal_code
                FROM equipment e
                JOIN dependencies d ON d.id = e.dependency_id
                JOIN locations l ON l.id = d.location_id
                WHERE e.id = ?
                """,
                (equipment_id,),
            ).fetchone()

    def save_equipment(self, values: dict[str, Any], equipment_id: int | None = None) -> int:
        duplicate = self.find_equipment_duplicate(values, exclude_id=equipment_id)
        if duplicate is not None:
            row, matched_field = duplicate
            description = " ".join(part for part in [str(row["brand"] or "").strip(), str(row["model"] or "").strip()] if part) or str(row["equipment_type"] or "Equipo")
            raise ValueError(f"Ya existe un equipo que coincide por {matched_field}: {description} — serie {row['serial_number'] or 'sin serie'} — dependencia {row['dependency_name']}.")
        with self.connect() as connection:
            assigned = str(values.get("assigned_user", "") or "").strip()
            person_id = None
            if assigned:
                connection.execute("INSERT OR IGNORE INTO atlas_people(full_name) VALUES(?)", (assigned,))
                person_id = connection.execute("SELECT id FROM atlas_people WHERE lower(trim(full_name))=lower(trim(?))", (assigned,)).fetchone()[0]
            params=(values["dependency_id"],person_id,values["equipment_type"],values["brand"],values["model"],values["serial_number"],values.get("inventory_number", ""),values["ip_address"],values["hostname"],values["status"],values["notes"])
            if equipment_id is None:
                cursor=connection.execute("""INSERT INTO atlas_equipment
                (dependency_id,assigned_person_id,equipment_type,brand,model,serial_number,inventory_number,ip_address,hostname,status,notes)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)""",params)
                return int(cursor.lastrowid)
            cursor = connection.execute("""UPDATE atlas_equipment SET dependency_id=?,assigned_person_id=?,equipment_type=?,brand=?,model=?,serial_number=?,inventory_number=?,ip_address=?,hostname=?,status=?,notes=?,updated_at=CURRENT_TIMESTAMP WHERE id=?""",params+(equipment_id,))
            if cursor.rowcount != 1:
                raise ValueError("El equipo seleccionado ya no existe o no pudo actualizarse.")
            connection.execute("UPDATE atlas_counter_readings SET serial_snapshot=?,model_snapshot=?,updated_at=CURRENT_TIMESTAMP WHERE equipment_id=?",(values["serial_number"],values["model"],equipment_id))
            saved = connection.execute("SELECT dependency_id,equipment_type,brand,model,serial_number,inventory_number,ip_address,hostname,status,notes FROM atlas_equipment WHERE id=?", (equipment_id,)).fetchone()
            expected = tuple(str(x or "") for x in (values["dependency_id"],values["equipment_type"],values["brand"],values["model"],values["serial_number"],values.get("inventory_number", ""),values["ip_address"],values["hostname"],values["status"],values["notes"]))
            actual = tuple(str(saved[k] or "") for k in ("dependency_id","equipment_type","brand","model","serial_number","inventory_number","ip_address","hostname","status","notes")) if saved else ()
            if actual != expected:
                raise RuntimeError("Atlas escribió el registro, pero la verificación posterior no coincidió.")
            return int(equipment_id)


    def editable_excel_rows(self) -> list[sqlite3.Row]:
        """Return one flat business row per equipment for editable Excel export."""
        with self.connect() as connection:
            return connection.execute(
                """
                SELECT
                    b.name AS building_name,
                    b.street AS street,
                    b.exterior_number AS exterior_number,
                    b.colony AS colony,
                    b.postal_code AS postal_code,
                    b.city AS city,
                    b.state AS state,
                    b.country AS country,
                    d.floor AS floor,
                    d.name AS dependency_name,
                    COALESCE(cta.full_name, '') AS cta_name,
                    d.phone AS dependency_phone,
                    d.email AS dependency_email,
                    COALESCE(o.name, '') AS office_name,
                    e.equipment_type AS equipment_type,
                    e.brand AS brand,
                    e.model AS model,
                    e.serial_number AS serial_number,
                    e.inventory_number AS inventory_number,
                    COALESCE(u.full_name, '') AS assigned_user,
                    e.ip_address AS ip_address,
                    e.hostname AS hostname,
                    e.status AS status,
                    e.notes AS equipment_notes
                FROM atlas_equipment e
                JOIN atlas_dependencies d ON d.id = e.dependency_id
                JOIN atlas_buildings b ON b.id = d.building_id
                LEFT JOIN atlas_offices o ON o.id = e.office_id
                LEFT JOIN atlas_people u ON u.id = e.assigned_person_id
                LEFT JOIN atlas_people cta ON cta.id = (
                    SELECT dp.person_id
                    FROM atlas_dependency_people dp
                    WHERE dp.dependency_id = d.id AND UPPER(dp.role) = 'CTA'
                    ORDER BY dp.person_id
                    LIMIT 1
                )
                ORDER BY b.name COLLATE NOCASE, d.name COLLATE NOCASE,
                         e.serial_number COLLATE NOCASE, e.id
                """
            ).fetchall()

    def equipment_duplicate_groups(self) -> list[dict[str, Any]]:
        """Detect true serial collisions using canonical equipment rows only.

        A duplicate group requires at least two *different equipment IDs*. This
        prevents compatibility/sync joins from making one equipment record
        appear twice and being offered as a false duplicate.
        """
        with self.connect() as connection:
            rows=connection.execute("""
                SELECT e.id,e.dependency_id,e.equipment_type,e.brand,e.model,e.serial_number,
                       e.inventory_number,e.ip_address,e.hostname,e.status,e.notes,
                       d.name AS dependency_name,b.name AS building_name
                FROM atlas_equipment e
                JOIN atlas_dependencies d ON d.id=e.dependency_id
                JOIN atlas_buildings b ON b.id=d.building_id
                WHERE trim(coalesce(e.serial_number,''))<>''
                ORDER BY e.serial_number COLLATE NOCASE,e.id
            """).fetchall()
        groups: dict[str,dict[int,sqlite3.Row]]={}
        for row in rows:
            key=self._normalize_equipment_identifier(row["serial_number"])
            if key:
                groups.setdefault(key,{})[int(row["id"])]=row
        result=[]
        for key, by_id in groups.items():
            records=list(by_id.values())
            if len(records)>1:
                result.append({"normalized_serial":key,"records":records})
        return result

    def merge_duplicate_equipment(self, keep_id: int, remove_ids: list[int]) -> int:
        """Merge references and useful blank fields into keep_id, then delete duplicates."""
        remove_ids = sorted({int(x) for x in remove_ids if int(x) != int(keep_id)})
        if not remove_ids:
            return int(keep_id)
        with self.connect() as connection:
            keep = connection.execute("SELECT * FROM atlas_equipment WHERE id=?", (keep_id,)).fetchone()
            if keep is None:
                raise ValueError("El equipo que se conservará ya no existe.")
            candidates = connection.execute(
                f"SELECT * FROM atlas_equipment WHERE id IN ({','.join('?' for _ in remove_ids)})",
                remove_ids,
            ).fetchall()
            if len(candidates) != len(remove_ids):
                raise ValueError("Uno o más equipos duplicados ya no existen.")
            keep_key = self._normalize_equipment_identifier(keep["serial_number"])
            if not keep_key or any(self._normalize_equipment_identifier(r["serial_number"]) != keep_key for r in candidates):
                raise ValueError("Solo se pueden fusionar registros con el mismo número de serie normalizado.")
            fields = ("equipment_type","brand","model","inventory_number","ip_address","hostname","status","notes")
            merged = {field: str(keep[field] or "").strip() for field in fields}
            for row in candidates:
                for field in fields:
                    value = str(row[field] or "").strip()
                    if not merged[field] and value:
                        merged[field] = value
            connection.execute("UPDATE atlas_counter_readings SET equipment_id=? WHERE equipment_id IN (%s)" % ','.join('?' for _ in remove_ids), [keep_id, *remove_ids])
            connection.execute("UPDATE atlas_service_orders SET equipment_id=? WHERE equipment_id IN (%s)" % ','.join('?' for _ in remove_ids), [keep_id, *remove_ids])
            # Avoid unique-index collisions while consolidating optional identifiers.
            for row in candidates:
                connection.execute("UPDATE atlas_equipment SET serial_number='',inventory_number='',hostname='' WHERE id=?", (int(row["id"]),))
            connection.execute("""UPDATE atlas_equipment SET equipment_type=?,brand=?,model=?,inventory_number=?,ip_address=?,hostname=?,status=?,notes=?,updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                tuple(merged[f] for f in fields) + (keep_id,))
            connection.execute("DELETE FROM atlas_equipment WHERE id IN (%s)" % ','.join('?' for _ in remove_ids), remove_ids)
            return int(keep_id)


    def dependency_choices_detailed(self) -> list[sqlite3.Row]:
        """Canonical dependency choices for service documents; one row per dependency."""
        with self.connect() as connection:
            return list(connection.execute(
                """
                SELECT d.id,d.name,d.court,d.tribunal,
                       COALESCE((SELECT o.name FROM atlas_offices o WHERE o.dependency_id=d.id ORDER BY o.id LIMIT 1),'') AS office,
                       COALESCE((SELECT p.full_name FROM atlas_dependency_people dp JOIN atlas_people p ON p.id=dp.person_id
                                 WHERE dp.dependency_id=d.id AND lower(dp.role)='cta' ORDER BY dp.person_id LIMIT 1),'') AS cta,
                       d.phone,d.email,d.notes, b.name AS building,d.floor,b.city,b.state,b.street,
                       b.exterior_number,b.colony,b.postal_code
                FROM atlas_dependencies d
                JOIN atlas_buildings b ON b.id=d.building_id
                WHERE d.active=1
                ORDER BY b.name COLLATE NOCASE,d.floor COLLATE NOCASE,d.name COLLATE NOCASE,d.id
                """
            ).fetchall())

    def equipment_choices_detailed(self) -> list[sqlite3.Row]:
        """Canonical equipment choices for service documents; one row per equipment record."""
        with self.connect() as connection:
            return list(connection.execute(
                """
                SELECT e.id,e.dependency_id,e.equipment_type,e.brand,e.model,e.serial_number,e.inventory_number,
                       e.ip_address,e.hostname,e.status,d.name AS dependency_name,
                       COALESCE((SELECT o.name FROM atlas_offices o WHERE o.id=e.office_id LIMIT 1),
                                (SELECT o.name FROM atlas_offices o WHERE o.dependency_id=d.id ORDER BY o.id LIMIT 1),'') AS office,
                       COALESCE((SELECT p.full_name FROM atlas_dependency_people dp JOIN atlas_people p ON p.id=dp.person_id
                                 WHERE dp.dependency_id=d.id AND lower(dp.role)='cta' ORDER BY dp.person_id LIMIT 1),'') AS cta,
                       d.phone,d.phone AS dependency_phone,d.email,b.name AS building,d.floor,b.city,b.state,b.street,
                       b.exterior_number,b.colony,b.postal_code
                FROM atlas_equipment e
                JOIN atlas_dependencies d ON d.id=e.dependency_id
                JOIN atlas_buildings b ON b.id=d.building_id
                WHERE d.active=1
                ORDER BY d.name COLLATE NOCASE,e.equipment_type COLLATE NOCASE,e.model COLLATE NOCASE,e.serial_number COLLATE NOCASE,e.id
                """
            ).fetchall())

    def list_service_formats(
        self, search: str = "", active_only: bool = False
    ) -> list[sqlite3.Row]:
        pattern = f"%{search.strip()}%"
        with self.connect() as connection:
            return list(connection.execute(
                """
                SELECT *
                FROM service_formats
                WHERE
                    (? = '%%' OR name LIKE ? OR description LIKE ?
                     OR document_type LIKE ? OR reported_issue LIKE ?)
                    AND (? = 0 OR active = 1)
                ORDER BY active DESC, name COLLATE NOCASE, id
                """,
                (pattern, pattern, pattern, pattern, pattern, int(active_only)),
            ).fetchall())

    def get_service_format(self, format_id: int) -> sqlite3.Row | None:
        with self.connect() as connection:
            return connection.execute(
                "SELECT * FROM service_formats WHERE id = ?",
                (format_id,),
            ).fetchone()

    def save_service_format(
        self, values: dict[str, Any], format_id: int | None = None
    ) -> int:
        columns = [
            "name", "document_type", "description",
            "validator_name", "validator_role", "validator_phone",
            "movement_type", "reported_issue", "diagnosis", "solution",
            "service_notes", "technician_name", "equipment_operates",
            "equipment_condition", "active",
        ]
        normalized = dict(values)
        normalized["name"] = str(values.get("name") or "").strip()
        if not normalized["name"]:
            raise ValueError("El nombre del formato es obligatorio.")
        normalized["active"] = 1 if values.get("active", True) else 0
        params = [normalized.get(column, "") for column in columns]

        try:
            with self.connect() as connection:
                if format_id is None:
                    placeholders = ", ".join("?" for _ in columns)
                    cursor = connection.execute(
                        f"INSERT INTO service_formats ({', '.join(columns)}) "
                        f"VALUES ({placeholders})",
                        params,
                    )
                    return int(cursor.lastrowid)

                assignments = ", ".join(f"{column} = ?" for column in columns)
                connection.execute(
                    f"""
                    UPDATE service_formats
                    SET {assignments}, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    params + [format_id],
                )
                return int(format_id)
        except sqlite3.IntegrityError as error:
            raise ValueError(
                f"Ya existe un formato llamado '{normalized['name']}'."
            ) from error

    def delete_service_format(self, format_id: int) -> None:
        with self.connect() as connection:
            connection.execute(
                "DELETE FROM service_formats WHERE id = ?",
                (format_id,),
            )

    def list_service_orders(self, search: str = "") -> list[sqlite3.Row]:
        pattern = f"%{search.strip()}%"
        with self.connect() as connection:
            return list(connection.execute(
                """
                SELECT
                    s.*,
                    e.equipment_type,
                    e.brand,
                    e.model,
                    e.serial_number,
                    d.name AS dependency_name
                FROM service_orders s
                LEFT JOIN equipment e ON e.id = s.equipment_id
                LEFT JOIN dependencies d ON d.id = s.dependency_id
                WHERE
                    ? = '%%'
                    OR s.folio LIKE ?
                    OR s.document_type LIKE ?
                    OR s.provider_report LIKE ?
                    OR e.serial_number LIKE ?
                    OR e.model LIKE ?
                    OR d.name LIKE ?
                ORDER BY s.created_at DESC, s.id DESC
                """,
                (pattern,) * 7,
            ).fetchall())

    def save_service_order(self, values: dict[str, Any], order_id: int | None = None) -> int:
        columns = [
            "folio", "document_type", "equipment_id", "dependency_id",
            "dgti_report", "provider_report", "report_date", "report_time",
            "responsible_name", "validator_name", "validator_role", "validator_phone",
            "movement_type", "reported_issue", "diagnosis",
            "diagnosis_date", "diagnosis_time", "solution",
            "solution_date", "solution_time", "service_notes", "technician_name",
            "equipment_operates", "equipment_condition", "output_path"
        ]
        params = [values.get(column) for column in columns]
        with self.connect() as connection:
            if order_id is None:
                placeholders = ", ".join("?" for _ in columns)
                cursor = connection.execute(
                    f"INSERT INTO service_orders ({', '.join(columns)}) VALUES ({placeholders})",
                    params,
                )
                return int(cursor.lastrowid)

            assignments = ", ".join(f"{column} = ?" for column in columns)
            connection.execute(
                f"""
                UPDATE service_orders
                SET {assignments}, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                params + [order_id],
            )
            return order_id

    def update_service_order_output(self, order_id: int, output_path: str) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE service_orders
                SET output_path = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (output_path, order_id),
            )

    def delete_service_order(self, order_id: int) -> None:
        with self.connect() as connection:
            connection.execute("DELETE FROM service_orders WHERE id = ?", (order_id,))

    @staticmethod
    def _counter_number(value: Any) -> float | int | None:
        if value is None or value == "":
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        if number.is_integer():
            return int(number)
        return number

    def _equipment_id_for_serial(
        self,
        connection: sqlite3.Connection,
        serial_number: str,
    ) -> int | None:
        normalized = self._normalize_equipment_identifier(serial_number)
        if not normalized:
            return None

        rows = connection.execute(
            "SELECT id, serial_number FROM equipment WHERE serial_number <> ''"
        ).fetchall()
        for row in rows:
            if (
                self._normalize_equipment_identifier(row["serial_number"])
                == normalized
            ):
                return int(row["id"])
        return None

    def save_counter_records(
        self,
        records: list[dict[str, Any]],
    ) -> dict[str, int]:
        inserted = 0
        updated = 0

        with self.connect() as connection:
            for record in records:
                record_uid = str(record.get("id") or "").strip()
                if not record_uid:
                    record_uid = str(uuid.uuid4())

                serial_number = str(
                    record.get("equipment")
                    or record.get("serial_number")
                    or ""
                ).strip()
                model = str(record.get("model") or "").strip()
                source_file = str(
                    record.get("file")
                    or record.get("source_file")
                    or ""
                ).strip()
                reading_date = str(
                    record.get("date")
                    or record.get("reading_date")
                    or ""
                ).strip()
                format_type = str(
                    record.get("format")
                    or record.get("format_type")
                    or ""
                ).strip()

                total = self._counter_number(record.get("total"))
                office = None
                letter = self._counter_number(
                    record.get("equivalent")
                    if "equivalent" in record
                    else record.get("letter_prints")
                )
                duplex = self._counter_number(
                    record.get("duplex")
                    if "duplex" in record
                    else record.get("duplex_sheets")
                )
                jams = self._counter_number(
                    record.get("jams")
                    if "jams" in record
                    else record.get("jam_events")
                )
                misfeeds = self._counter_number(
                    record.get("misfeeds")
                    if "misfeeds" in record
                    else record.get("misfeed_events")
                )
                economode = self._counter_number(
                    record.get("economode")
                    if "economode" in record
                    else record.get("economode_prints")
                )

                equipment_id = self._equipment_id_for_serial(
                    connection,
                    serial_number,
                )

                exists = connection.execute(
                    "SELECT 1 FROM counter_records WHERE record_uid = ?",
                    (record_uid,),
                ).fetchone()

                connection.execute(
                    """
                    INSERT INTO counter_records (
                        record_uid, equipment_id, reading_date, serial_number,
                        model, source_file, total_prints, office_prints,
                        letter_prints, duplex_sheets, jam_events,
                        misfeed_events, economode_prints, format_type
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(record_uid) DO UPDATE SET
                        equipment_id = excluded.equipment_id,
                        reading_date = excluded.reading_date,
                        serial_number = excluded.serial_number,
                        model = excluded.model,
                        source_file = excluded.source_file,
                        total_prints = excluded.total_prints,
                        office_prints = excluded.office_prints,
                        letter_prints = excluded.letter_prints,
                        duplex_sheets = excluded.duplex_sheets,
                        jam_events = excluded.jam_events,
                        misfeed_events = excluded.misfeed_events,
                        economode_prints = excluded.economode_prints,
                        format_type = excluded.format_type,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        record_uid,
                        equipment_id,
                        reading_date,
                        serial_number,
                        model,
                        source_file,
                        total,
                        office,
                        letter,
                        duplex,
                        jams,
                        misfeeds,
                        economode,
                        format_type,
                    ),
                )

                if exists:
                    updated += 1
                else:
                    inserted += 1

        return {
            "inserted": inserted,
            "updated": updated,
            "saved": inserted + updated,
        }

    def list_counter_records(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    record_uid,
                    reading_date,
                    serial_number,
                    model,
                    source_file,
                    total_prints,
                    office_prints,
                    letter_prints,
                    duplex_sheets,
                    jam_events,
                    misfeed_events,
                    economode_prints,
                    format_type
                FROM counter_records
                ORDER BY
                    CASE WHEN reading_date = '' THEN 1 ELSE 0 END,
                    reading_date DESC,
                    id DESC
                """
            ).fetchall()

        return [
            {
                "id": row["record_uid"],
                "date": row["reading_date"],
                "equipment": row["serial_number"],
                "model": row["model"],
                "file": row["source_file"],
                "total": row["total_prints"],
                "equivalent": row["letter_prints"],
                "duplex": row["duplex_sheets"],
                "jams": row["jam_events"],
                "misfeeds": row["misfeed_events"],
                "economode": row["economode_prints"],
                "format": row["format_type"],
            }
            for row in rows
        ]

    def delete_counter_record(self, record_uid: str) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM counter_records WHERE record_uid = ?",
                (record_uid,),
            )
            return cursor.rowcount > 0

    def clear_counter_records(self) -> int:
        with self.connect() as connection:
            count = int(
                connection.execute(
                    "SELECT COUNT(*) FROM counter_records"
                ).fetchone()[0]
            )
            connection.execute("DELETE FROM counter_records")
            return count

    def counter_record_count(self) -> int:
        with self.connect() as connection:
            return int(
                connection.execute(
                    "SELECT COUNT(*) FROM counter_records"
                ).fetchone()[0]
            )

    def delete_equipment(self, equipment_id: int) -> None:
        with self.connect() as connection:
            connection.execute(
                "DELETE FROM equipment WHERE id = ?",
                (equipment_id,),
            )
