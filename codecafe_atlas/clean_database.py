from __future__ import annotations

import shutil
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

CLEAN_SCHEMA_VERSION = "3"

STORAGE_SCHEMA = r"""
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS atlas_buildings(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 name TEXT NOT NULL COLLATE NOCASE UNIQUE,
 street TEXT NOT NULL DEFAULT '', exterior_number TEXT NOT NULL DEFAULT '', colony TEXT NOT NULL DEFAULT '',
 city TEXT NOT NULL DEFAULT '', state TEXT NOT NULL DEFAULT '', postal_code TEXT NOT NULL DEFAULT '',
 country TEXT NOT NULL DEFAULT 'México', notes TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS atlas_people(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 full_name TEXT NOT NULL COLLATE NOCASE,
 phone TEXT NOT NULL DEFAULT '', email TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_atlas_people_name ON atlas_people(lower(trim(full_name)));
CREATE TABLE IF NOT EXISTS atlas_dependencies(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 building_id INTEGER NOT NULL REFERENCES atlas_buildings(id) ON DELETE RESTRICT,
 name TEXT NOT NULL COLLATE NOCASE, court TEXT NOT NULL DEFAULT '', tribunal TEXT NOT NULL DEFAULT '',
 floor TEXT NOT NULL DEFAULT '', phone TEXT NOT NULL DEFAULT '', email TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '',
 active INTEGER NOT NULL DEFAULT 1 CHECK(active IN(0,1)),
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(building_id,name,floor)
);
CREATE TABLE IF NOT EXISTS atlas_offices(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 dependency_id INTEGER NOT NULL REFERENCES atlas_dependencies(id) ON DELETE CASCADE,
 name TEXT NOT NULL COLLATE NOCASE, notes TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(dependency_id,name)
);
CREATE TABLE IF NOT EXISTS atlas_dependency_people(
 dependency_id INTEGER NOT NULL REFERENCES atlas_dependencies(id) ON DELETE CASCADE,
 person_id INTEGER NOT NULL REFERENCES atlas_people(id) ON DELETE RESTRICT,
 role TEXT NOT NULL COLLATE NOCASE,
 PRIMARY KEY(dependency_id,person_id,role)
);
CREATE TABLE IF NOT EXISTS atlas_equipment(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 dependency_id INTEGER NOT NULL REFERENCES atlas_dependencies(id) ON DELETE RESTRICT,
 office_id INTEGER REFERENCES atlas_offices(id) ON DELETE SET NULL,
 assigned_person_id INTEGER REFERENCES atlas_people(id) ON DELETE SET NULL,
 equipment_type TEXT NOT NULL DEFAULT '', brand TEXT NOT NULL DEFAULT '', model TEXT NOT NULL DEFAULT '',
 serial_number TEXT NOT NULL DEFAULT '', inventory_number TEXT NOT NULL DEFAULT '', ip_address TEXT NOT NULL DEFAULT '',
 hostname TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'Activo', notes TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_atlas_equipment_serial ON atlas_equipment(lower(trim(serial_number))) WHERE trim(serial_number)<>'';
CREATE UNIQUE INDEX IF NOT EXISTS uq_atlas_equipment_inventory ON atlas_equipment(lower(trim(inventory_number))) WHERE trim(inventory_number)<>'';
CREATE UNIQUE INDEX IF NOT EXISTS uq_atlas_equipment_hostname ON atlas_equipment(lower(trim(hostname))) WHERE trim(hostname)<>'';
CREATE INDEX IF NOT EXISTS idx_atlas_equipment_dependency ON atlas_equipment(dependency_id);
CREATE TABLE IF NOT EXISTS atlas_counter_readings(
 id INTEGER PRIMARY KEY AUTOINCREMENT, external_uid TEXT NOT NULL UNIQUE,
 equipment_id INTEGER REFERENCES atlas_equipment(id) ON DELETE SET NULL,
 reading_date TEXT NOT NULL DEFAULT '', serial_snapshot TEXT NOT NULL DEFAULT '', model_snapshot TEXT NOT NULL DEFAULT '',
 source_file TEXT NOT NULL DEFAULT '', total_prints REAL, office_prints REAL, letter_prints REAL, duplex_sheets REAL,
 jam_events REAL, misfeed_events REAL, economode_prints REAL, format_type TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_atlas_counter_equipment_date ON atlas_counter_readings(equipment_id,reading_date DESC,id DESC);
CREATE TABLE IF NOT EXISTS atlas_service_orders(
 id INTEGER PRIMARY KEY AUTOINCREMENT, folio TEXT NOT NULL DEFAULT '', document_type TEXT NOT NULL DEFAULT 'Cédula de Servicio',
 equipment_id INTEGER REFERENCES atlas_equipment(id) ON DELETE SET NULL,
 dependency_id INTEGER REFERENCES atlas_dependencies(id) ON DELETE SET NULL,
 dgti_report TEXT NOT NULL DEFAULT '', provider_report TEXT NOT NULL DEFAULT '', report_date TEXT NOT NULL DEFAULT '', report_time TEXT NOT NULL DEFAULT '',
 responsible_name TEXT NOT NULL DEFAULT '', validator_name TEXT NOT NULL DEFAULT '', validator_role TEXT NOT NULL DEFAULT '', validator_phone TEXT NOT NULL DEFAULT '',
 movement_type TEXT NOT NULL DEFAULT '', reported_issue TEXT NOT NULL DEFAULT '', diagnosis TEXT NOT NULL DEFAULT '', diagnosis_date TEXT NOT NULL DEFAULT '', diagnosis_time TEXT NOT NULL DEFAULT '',
 solution TEXT NOT NULL DEFAULT '', solution_date TEXT NOT NULL DEFAULT '', solution_time TEXT NOT NULL DEFAULT '', service_notes TEXT NOT NULL DEFAULT '', technician_name TEXT NOT NULL DEFAULT '',
 equipment_operates TEXT NOT NULL DEFAULT '', equipment_condition TEXT NOT NULL DEFAULT '', output_path TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS service_formats(
 id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL COLLATE NOCASE UNIQUE, document_type TEXT NOT NULL DEFAULT 'Cédula de Servicio',
 description TEXT NOT NULL DEFAULT '', validator_name TEXT NOT NULL DEFAULT '', validator_role TEXT NOT NULL DEFAULT '', validator_phone TEXT NOT NULL DEFAULT '',
 movement_type TEXT NOT NULL DEFAULT '', reported_issue TEXT NOT NULL DEFAULT '', diagnosis TEXT NOT NULL DEFAULT '', solution TEXT NOT NULL DEFAULT '', service_notes TEXT NOT NULL DEFAULT '',
 technician_name TEXT NOT NULL DEFAULT '', equipment_operates TEXT NOT NULL DEFAULT 'Sí', equipment_condition TEXT NOT NULL DEFAULT 'No', active INTEGER NOT NULL DEFAULT 1,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS app_metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL DEFAULT '',updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS sync_metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS atlas_sync_records(
 entity_type TEXT NOT NULL, entity_id INTEGER NOT NULL, record_uuid TEXT NOT NULL UNIQUE,
 revision INTEGER NOT NULL DEFAULT 1, created_by_installation TEXT NOT NULL DEFAULT '', updated_by_installation TEXT NOT NULL DEFAULT '', deleted_at TEXT,
 PRIMARY KEY(entity_type,entity_id)
);
CREATE TABLE IF NOT EXISTS atlas_location_input(
 id INTEGER PRIMARY KEY AUTOINCREMENT, building_id INTEGER, building TEXT NOT NULL DEFAULT '', city TEXT NOT NULL DEFAULT '', state TEXT NOT NULL DEFAULT '',
 street TEXT NOT NULL DEFAULT '', exterior_number TEXT NOT NULL DEFAULT '', colony TEXT NOT NULL DEFAULT '', postal_code TEXT NOT NULL DEFAULT '', floor TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
PRAGMA user_version=3;
"""

VIEW_SCHEMA = r"""
DROP VIEW IF EXISTS buildings; DROP VIEW IF EXISTS locations; DROP VIEW IF EXISTS dependencies; DROP VIEW IF EXISTS equipment; DROP VIEW IF EXISTS counter_records; DROP VIEW IF EXISTS service_orders;
CREATE VIEW buildings AS
SELECT b.id,b.name,trim(b.street||CASE WHEN b.exterior_number<>'' THEN ' '||b.exterior_number ELSE '' END||CASE WHEN b.colony<>'' THEN ', '||b.colony ELSE '' END||CASE WHEN b.city<>'' THEN ', '||b.city ELSE '' END||CASE WHEN b.state<>'' THEN ', '||b.state ELSE '' END||CASE WHEN b.postal_code<>'' THEN ' CP '||b.postal_code ELSE '' END) AS address,b.notes,b.created_at,b.updated_at,
 s.record_uuid,s.created_by_installation,s.updated_by_installation,s.revision,s.deleted_at
FROM atlas_buildings b LEFT JOIN atlas_sync_records s ON s.entity_type='buildings' AND s.entity_id=b.id;
CREATE VIEW locations AS
SELECT d.id,d.building_id,b.name AS building,b.city,b.state,b.street,b.exterior_number,b.colony,b.postal_code,d.floor,d.created_at,d.updated_at,
 s.record_uuid,s.created_by_installation,s.updated_by_installation,s.revision,s.deleted_at
FROM atlas_dependencies d JOIN atlas_buildings b ON b.id=d.building_id LEFT JOIN atlas_sync_records s ON s.entity_type='locations' AND s.entity_id=d.id
UNION ALL
SELECT i.id,i.building_id,i.building,i.city,i.state,i.street,i.exterior_number,i.colony,i.postal_code,i.floor,i.created_at,i.updated_at,NULL,'','',1,NULL
FROM atlas_location_input i WHERE NOT EXISTS(SELECT 1 FROM atlas_dependencies d WHERE d.id=i.id);
CREATE VIEW dependencies AS
SELECT d.id,d.id AS location_id,d.name,d.court,d.tribunal,coalesce(o.name,'') AS office,coalesce(p.full_name,'') AS cta,d.phone,d.email,d.notes,d.active,d.created_at,d.updated_at,
 s.record_uuid,s.created_by_installation,s.updated_by_installation,s.revision,s.deleted_at
FROM atlas_dependencies d
LEFT JOIN atlas_offices o ON o.id=(SELECT min(o2.id) FROM atlas_offices o2 WHERE o2.dependency_id=d.id)
LEFT JOIN atlas_dependency_people dp ON dp.dependency_id=d.id AND lower(dp.role)='cta'
LEFT JOIN atlas_people p ON p.id=dp.person_id
LEFT JOIN atlas_sync_records s ON s.entity_type='dependencies' AND s.entity_id=d.id;
CREATE VIEW equipment AS
SELECT e.id,e.dependency_id,e.equipment_type,e.brand,e.model,e.serial_number,e.inventory_number,coalesce(p.full_name,'') AS assigned_user,e.ip_address,e.hostname,e.status,e.notes,e.created_at,e.updated_at,
 s.record_uuid,s.created_by_installation,s.updated_by_installation,s.revision,s.deleted_at
FROM atlas_equipment e LEFT JOIN atlas_people p ON p.id=e.assigned_person_id LEFT JOIN atlas_sync_records s ON s.entity_type='equipment' AND s.entity_id=e.id;
CREATE VIEW counter_records AS
SELECT c.id,c.external_uid AS record_uid,c.equipment_id,c.reading_date,c.serial_snapshot AS serial_number,c.model_snapshot AS model,c.source_file,c.total_prints,c.office_prints,c.letter_prints,c.duplex_sheets,c.jam_events,c.misfeed_events,c.economode_prints,c.format_type,c.created_at,c.updated_at,
 s.record_uuid,s.created_by_installation,s.updated_by_installation,s.revision,s.deleted_at
FROM atlas_counter_readings c LEFT JOIN atlas_sync_records s ON s.entity_type='counter_records' AND s.entity_id=c.id;
CREATE VIEW service_orders AS
SELECT o.*,s.record_uuid,s.created_by_installation,s.updated_by_installation,s.revision,s.deleted_at
FROM atlas_service_orders o LEFT JOIN atlas_sync_records s ON s.entity_type='service_orders' AND s.entity_id=o.id;
"""

TRIGGERS = r"""
DROP TRIGGER IF EXISTS buildings_insert; DROP TRIGGER IF EXISTS buildings_update; DROP TRIGGER IF EXISTS buildings_delete;
CREATE TRIGGER buildings_insert INSTEAD OF INSERT ON buildings BEGIN
 INSERT INTO atlas_buildings(id,name,notes,created_at,updated_at) VALUES(NEW.id,NEW.name,coalesce(NEW.notes,''),coalesce(NEW.created_at,CURRENT_TIMESTAMP),coalesce(NEW.updated_at,CURRENT_TIMESTAMP));
 INSERT OR IGNORE INTO atlas_sync_records(entity_type,entity_id,record_uuid,revision,created_by_installation,updated_by_installation,deleted_at) VALUES('buildings',last_insert_rowid(),coalesce(NEW.record_uuid,lower(hex(randomblob(16)))),coalesce(NEW.revision,1),coalesce(NEW.created_by_installation,''),coalesce(NEW.updated_by_installation,''),NEW.deleted_at);
END;
CREATE TRIGGER buildings_update INSTEAD OF UPDATE ON buildings BEGIN
 UPDATE atlas_buildings SET name=NEW.name,notes=NEW.notes,updated_at=coalesce(NEW.updated_at,CURRENT_TIMESTAMP) WHERE id=OLD.id;
 UPDATE atlas_sync_records SET record_uuid=coalesce(NEW.record_uuid,record_uuid),revision=coalesce(NEW.revision,revision),updated_by_installation=coalesce(NEW.updated_by_installation,updated_by_installation),deleted_at=NEW.deleted_at WHERE entity_type='buildings' AND entity_id=OLD.id;
END;
CREATE TRIGGER buildings_delete INSTEAD OF DELETE ON buildings BEGIN DELETE FROM atlas_buildings WHERE id=OLD.id; END;

DROP TRIGGER IF EXISTS locations_insert; DROP TRIGGER IF EXISTS locations_update; DROP TRIGGER IF EXISTS locations_delete;
CREATE TRIGGER locations_insert INSTEAD OF INSERT ON locations BEGIN
 INSERT INTO atlas_location_input(id,building_id,building,city,state,street,exterior_number,colony,postal_code,floor,created_at,updated_at)
 VALUES(NEW.id,NEW.building_id,coalesce(NEW.building,''),coalesce(NEW.city,''),coalesce(NEW.state,''),coalesce(NEW.street,''),coalesce(NEW.exterior_number,''),coalesce(NEW.colony,''),coalesce(NEW.postal_code,''),coalesce(NEW.floor,''),coalesce(NEW.created_at,CURRENT_TIMESTAMP),coalesce(NEW.updated_at,CURRENT_TIMESTAMP));
END;
CREATE TRIGGER locations_update INSTEAD OF UPDATE ON locations BEGIN
 UPDATE atlas_dependencies SET building_id=coalesce(NEW.building_id,building_id),floor=NEW.floor,updated_at=CURRENT_TIMESTAMP WHERE id=OLD.id;
 UPDATE atlas_buildings SET name=CASE WHEN trim(NEW.building)<>'' THEN NEW.building ELSE name END,city=NEW.city,state=NEW.state,street=NEW.street,exterior_number=NEW.exterior_number,colony=NEW.colony,postal_code=NEW.postal_code,updated_at=CURRENT_TIMESTAMP WHERE id=(SELECT building_id FROM atlas_dependencies WHERE id=OLD.id);
 UPDATE atlas_location_input SET building_id=NEW.building_id,building=NEW.building,city=NEW.city,state=NEW.state,street=NEW.street,exterior_number=NEW.exterior_number,colony=NEW.colony,postal_code=NEW.postal_code,floor=NEW.floor,updated_at=CURRENT_TIMESTAMP WHERE id=OLD.id;
END;
CREATE TRIGGER locations_delete INSTEAD OF DELETE ON locations BEGIN DELETE FROM atlas_location_input WHERE id=OLD.id; END;

DROP TRIGGER IF EXISTS dependencies_insert; DROP TRIGGER IF EXISTS dependencies_update; DROP TRIGGER IF EXISTS dependencies_delete;
CREATE TRIGGER dependencies_insert INSTEAD OF INSERT ON dependencies BEGIN
 INSERT INTO atlas_buildings(name,city,state,street,exterior_number,colony,postal_code)
 SELECT coalesce(nullif(trim(i.building),''),'Sin edificio'),i.city,i.state,i.street,i.exterior_number,i.colony,i.postal_code FROM atlas_location_input i WHERE i.id=NEW.location_id
 ON CONFLICT(name) DO UPDATE SET city=excluded.city,state=excluded.state,street=excluded.street,exterior_number=excluded.exterior_number,colony=excluded.colony,postal_code=excluded.postal_code;
 INSERT INTO atlas_dependencies(id,building_id,name,court,tribunal,floor,phone,email,notes,active,created_at,updated_at)
 SELECT NEW.location_id,coalesce(i.building_id,(SELECT id FROM atlas_buildings WHERE name=i.building COLLATE NOCASE)),NEW.name,coalesce(NEW.court,''),coalesce(NEW.tribunal,''),i.floor,coalesce(NEW.phone,''),coalesce(NEW.email,''),coalesce(NEW.notes,''),coalesce(NEW.active,1),coalesce(NEW.created_at,CURRENT_TIMESTAMP),coalesce(NEW.updated_at,CURRENT_TIMESTAMP) FROM atlas_location_input i WHERE i.id=NEW.location_id;
 INSERT INTO atlas_offices(dependency_id,name) SELECT NEW.location_id,trim(NEW.office) WHERE trim(coalesce(NEW.office,''))<>'';
 INSERT OR IGNORE INTO atlas_people(full_name,phone,email) SELECT trim(NEW.cta),coalesce(NEW.phone,''),coalesce(NEW.email,'') WHERE trim(coalesce(NEW.cta,''))<>'';
 INSERT INTO atlas_dependency_people(dependency_id,person_id,role) SELECT NEW.location_id,id,'CTA' FROM atlas_people WHERE lower(trim(full_name))=lower(trim(NEW.cta)) AND trim(coalesce(NEW.cta,''))<>'';
 DELETE FROM atlas_location_input WHERE id=NEW.location_id;
END;
CREATE TRIGGER dependencies_update INSTEAD OF UPDATE ON dependencies BEGIN
 UPDATE atlas_dependencies SET name=NEW.name,court=NEW.court,tribunal=NEW.tribunal,phone=NEW.phone,email=NEW.email,notes=NEW.notes,active=NEW.active,updated_at=coalesce(NEW.updated_at,CURRENT_TIMESTAMP) WHERE id=OLD.id;
 DELETE FROM atlas_offices WHERE dependency_id=OLD.id; INSERT INTO atlas_offices(dependency_id,name) SELECT OLD.id,trim(NEW.office) WHERE trim(coalesce(NEW.office,''))<>'';
 DELETE FROM atlas_dependency_people WHERE dependency_id=OLD.id AND lower(role)='cta';
 INSERT OR IGNORE INTO atlas_people(full_name,phone,email) SELECT trim(NEW.cta),coalesce(NEW.phone,''),coalesce(NEW.email,'') WHERE trim(coalesce(NEW.cta,''))<>'';
 INSERT INTO atlas_dependency_people(dependency_id,person_id,role) SELECT OLD.id,id,'CTA' FROM atlas_people WHERE lower(trim(full_name))=lower(trim(NEW.cta)) AND trim(coalesce(NEW.cta,''))<>'';
END;
CREATE TRIGGER dependencies_delete INSTEAD OF DELETE ON dependencies BEGIN DELETE FROM atlas_dependencies WHERE id=OLD.id; END;

DROP TRIGGER IF EXISTS equipment_insert; DROP TRIGGER IF EXISTS equipment_update; DROP TRIGGER IF EXISTS equipment_delete;
CREATE TRIGGER equipment_insert INSTEAD OF INSERT ON equipment BEGIN
 INSERT OR IGNORE INTO atlas_people(full_name) SELECT trim(NEW.assigned_user) WHERE trim(coalesce(NEW.assigned_user,''))<>'';
 INSERT INTO atlas_equipment(id,dependency_id,assigned_person_id,equipment_type,brand,model,serial_number,inventory_number,ip_address,hostname,status,notes,created_at,updated_at)
 VALUES(NEW.id,NEW.dependency_id,(SELECT id FROM atlas_people WHERE lower(trim(full_name))=lower(trim(NEW.assigned_user))),coalesce(NEW.equipment_type,''),coalesce(NEW.brand,''),coalesce(NEW.model,''),coalesce(NEW.serial_number,''),coalesce(NEW.inventory_number,''),coalesce(NEW.ip_address,''),coalesce(NEW.hostname,''),coalesce(NEW.status,'Activo'),coalesce(NEW.notes,''),coalesce(NEW.created_at,CURRENT_TIMESTAMP),coalesce(NEW.updated_at,CURRENT_TIMESTAMP));
END;
CREATE TRIGGER equipment_update INSTEAD OF UPDATE ON equipment BEGIN
 INSERT OR IGNORE INTO atlas_people(full_name) SELECT trim(NEW.assigned_user) WHERE trim(coalesce(NEW.assigned_user,''))<>'';
 UPDATE atlas_equipment SET dependency_id=NEW.dependency_id,assigned_person_id=(SELECT id FROM atlas_people WHERE lower(trim(full_name))=lower(trim(NEW.assigned_user))),equipment_type=NEW.equipment_type,brand=NEW.brand,model=NEW.model,serial_number=NEW.serial_number,inventory_number=NEW.inventory_number,ip_address=NEW.ip_address,hostname=NEW.hostname,status=NEW.status,notes=NEW.notes,updated_at=coalesce(NEW.updated_at,CURRENT_TIMESTAMP) WHERE id=OLD.id;
END;
CREATE TRIGGER equipment_delete INSTEAD OF DELETE ON equipment BEGIN DELETE FROM atlas_equipment WHERE id=OLD.id; END;

DROP TRIGGER IF EXISTS counter_insert; DROP TRIGGER IF EXISTS counter_update; DROP TRIGGER IF EXISTS counter_delete;
CREATE TRIGGER counter_insert INSTEAD OF INSERT ON counter_records BEGIN
 INSERT INTO atlas_counter_readings(id,external_uid,equipment_id,reading_date,serial_snapshot,model_snapshot,source_file,total_prints,office_prints,letter_prints,duplex_sheets,jam_events,misfeed_events,economode_prints,format_type,created_at,updated_at)
 VALUES(NEW.id,NEW.record_uid,NEW.equipment_id,NEW.reading_date,NEW.serial_number,NEW.model,NEW.source_file,NEW.total_prints,NEW.office_prints,NEW.letter_prints,NEW.duplex_sheets,NEW.jam_events,NEW.misfeed_events,NEW.economode_prints,NEW.format_type,coalesce(NEW.created_at,CURRENT_TIMESTAMP),coalesce(NEW.updated_at,CURRENT_TIMESTAMP))
 ON CONFLICT(external_uid) DO UPDATE SET equipment_id=excluded.equipment_id,reading_date=excluded.reading_date,serial_snapshot=excluded.serial_snapshot,model_snapshot=excluded.model_snapshot,source_file=excluded.source_file,total_prints=excluded.total_prints,office_prints=excluded.office_prints,letter_prints=excluded.letter_prints,duplex_sheets=excluded.duplex_sheets,jam_events=excluded.jam_events,misfeed_events=excluded.misfeed_events,economode_prints=excluded.economode_prints,format_type=excluded.format_type,updated_at=CURRENT_TIMESTAMP;
END;
CREATE TRIGGER counter_update INSTEAD OF UPDATE ON counter_records BEGIN UPDATE atlas_counter_readings SET equipment_id=NEW.equipment_id,reading_date=NEW.reading_date,serial_snapshot=NEW.serial_number,model_snapshot=NEW.model,source_file=NEW.source_file,total_prints=NEW.total_prints,office_prints=NEW.office_prints,letter_prints=NEW.letter_prints,duplex_sheets=NEW.duplex_sheets,jam_events=NEW.jam_events,misfeed_events=NEW.misfeed_events,economode_prints=NEW.economode_prints,format_type=NEW.format_type,updated_at=CURRENT_TIMESTAMP WHERE id=OLD.id; END;
CREATE TRIGGER counter_delete INSTEAD OF DELETE ON counter_records BEGIN DELETE FROM atlas_counter_readings WHERE id=OLD.id; END;

DROP TRIGGER IF EXISTS service_orders_insert; DROP TRIGGER IF EXISTS service_orders_update; DROP TRIGGER IF EXISTS service_orders_delete;
CREATE TRIGGER service_orders_insert INSTEAD OF INSERT ON service_orders BEGIN
 INSERT INTO atlas_service_orders(id,folio,document_type,equipment_id,dependency_id,dgti_report,provider_report,report_date,report_time,responsible_name,validator_name,validator_role,validator_phone,movement_type,reported_issue,diagnosis,diagnosis_date,diagnosis_time,solution,solution_date,solution_time,service_notes,technician_name,equipment_operates,equipment_condition,output_path,created_at,updated_at)
 VALUES(NEW.id,NEW.folio,NEW.document_type,NEW.equipment_id,NEW.dependency_id,NEW.dgti_report,NEW.provider_report,NEW.report_date,NEW.report_time,NEW.responsible_name,NEW.validator_name,NEW.validator_role,NEW.validator_phone,NEW.movement_type,NEW.reported_issue,NEW.diagnosis,NEW.diagnosis_date,NEW.diagnosis_time,NEW.solution,NEW.solution_date,NEW.solution_time,NEW.service_notes,NEW.technician_name,NEW.equipment_operates,NEW.equipment_condition,NEW.output_path,coalesce(NEW.created_at,CURRENT_TIMESTAMP),coalesce(NEW.updated_at,CURRENT_TIMESTAMP)); END;
CREATE TRIGGER service_orders_update INSTEAD OF UPDATE ON service_orders BEGIN
 UPDATE atlas_service_orders SET folio=NEW.folio,document_type=NEW.document_type,equipment_id=NEW.equipment_id,dependency_id=NEW.dependency_id,dgti_report=NEW.dgti_report,provider_report=NEW.provider_report,report_date=NEW.report_date,report_time=NEW.report_time,responsible_name=NEW.responsible_name,validator_name=NEW.validator_name,validator_role=NEW.validator_role,validator_phone=NEW.validator_phone,movement_type=NEW.movement_type,reported_issue=NEW.reported_issue,diagnosis=NEW.diagnosis,diagnosis_date=NEW.diagnosis_date,diagnosis_time=NEW.diagnosis_time,solution=NEW.solution,solution_date=NEW.solution_date,solution_time=NEW.solution_time,service_notes=NEW.service_notes,technician_name=NEW.technician_name,equipment_operates=NEW.equipment_operates,equipment_condition=NEW.equipment_condition,output_path=NEW.output_path,updated_at=CURRENT_TIMESTAMP WHERE id=OLD.id; END;
CREATE TRIGGER service_orders_delete INSTEAD OF DELETE ON service_orders BEGIN DELETE FROM atlas_service_orders WHERE id=OLD.id; END;
"""

def _table_exists(c: sqlite3.Connection, name: str) -> bool:
 return c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone() is not None

def _view_exists(c: sqlite3.Connection, name: str) -> bool:
 return c.execute("SELECT 1 FROM sqlite_master WHERE type='view' AND name=?",(name,)).fetchone() is not None

def _ensure_clean_sync_records(c: sqlite3.Connection) -> None:
 installation_row=c.execute("SELECT value FROM sync_metadata WHERE key='installation_uuid'").fetchone()
 installation_uuid=(installation_row[0] if installation_row and installation_row[0] else str(uuid.uuid4()))
 c.execute("INSERT OR REPLACE INTO sync_metadata(key,value,updated_at) VALUES('installation_uuid',?,CURRENT_TIMESTAMP)",(installation_uuid,))
 entity_tables={
  'buildings':'atlas_buildings',
  'locations':'atlas_dependencies',
  'dependencies':'atlas_dependencies',
  'equipment':'atlas_equipment',
  'counter_records':'atlas_counter_readings',
  'service_orders':'atlas_service_orders',
 }
 for entity_type,table in entity_tables.items():
  ids=[int(r[0]) for r in c.execute(f'SELECT id FROM {table}')]
  for entity_id in ids:
   row=c.execute('SELECT record_uuid FROM atlas_sync_records WHERE entity_type=? AND entity_id=?',(entity_type,entity_id)).fetchone()
   if row is None:
    c.execute('INSERT INTO atlas_sync_records(entity_type,entity_id,record_uuid,revision,created_by_installation,updated_by_installation) VALUES(?,?,?,?,?,?)',(entity_type,entity_id,str(uuid.uuid4()),1,installation_uuid,installation_uuid))
   elif not str(row[0] or '').strip():
    c.execute('UPDATE atlas_sync_records SET record_uuid=?,revision=CASE WHEN revision<1 THEN 1 ELSE revision END,created_by_installation=CASE WHEN trim(created_by_installation)="" THEN ? ELSE created_by_installation END,updated_by_installation=CASE WHEN trim(updated_by_installation)="" THEN ? ELSE updated_by_installation END WHERE entity_type=? AND entity_id=?',(str(uuid.uuid4()),installation_uuid,installation_uuid,entity_type,entity_id))
 c.commit()

def ensure_clean_database(path: Path) -> None:
 path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
 if not path.exists() or path.stat().st_size == 0:
  c=sqlite3.connect(path); c.executescript(STORAGE_SCHEMA); c.executescript(VIEW_SCHEMA); c.executescript(TRIGGERS); _seed(c); c.commit(); c.close(); return

 c=sqlite3.connect(path)
 try:
  tables={str(r[0]).lower() for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
  user_version=int(c.execute('PRAGMA user_version').fetchone()[0])
  clean_required={'atlas_buildings','atlas_dependencies','atlas_equipment','atlas_counter_readings','atlas_service_orders'}
  legacy_required={'buildings','locations','dependencies','equipment'}
  clean=clean_required.issubset(tables) and user_version>=3
  legacy=legacy_required.issubset(tables)
  if clean:
   _ensure_clean_sync_records(c)
   return
 finally:
  c.close()

 if not legacy:
  raise RuntimeError(
   'La base activa no coincide con un esquema Atlas compatible. '
   'No se modificó el archivo. Usa Administrar datos para previsualizar e importar una base compatible.'
  )

 backup=path.with_name(path.stem+'_legacy_backup_'+datetime.now().strftime('%Y%m%d_%H%M%S')+path.suffix)
 shutil.copy2(path,backup)
 tmp=path.with_suffix(path.suffix+'.cleaning')
 if tmp.exists(): tmp.unlink()
 _migrate_legacy(path,tmp)
 tmp.replace(path)

def _seed(c):
 for k,v in {'application_family':'CodeCafe Atlas','application_id':'io.codecafe.atlas','origin_id':'CCA-JSS-2026','database_format':'codecafe-atlas-clean','schema_version':CLEAN_SCHEMA_VERSION,'workspace_name':'codecafe-atlas','organization_name':'','workspace_description':''}.items():
  c.execute('INSERT OR IGNORE INTO app_metadata(key,value) VALUES(?,?)',(k,v))
 c.execute("INSERT OR IGNORE INTO sync_metadata(key,value) VALUES('installation_uuid',?)",(str(uuid.uuid4()),))

def _migrate_legacy(source: Path,target: Path) -> None:
 src=sqlite3.connect(source); src.row_factory=sqlite3.Row
 dst=sqlite3.connect(target); dst.row_factory=sqlite3.Row; dst.executescript(STORAGE_SCHEMA)
 try:
  dst.execute('BEGIN')
  loc_by_build={}
  for r in src.execute('SELECT * FROM locations ORDER BY id'):
   if r['building_id'] and r['building_id'] not in loc_by_build: loc_by_build[r['building_id']]=r
  for r in src.execute('SELECT * FROM buildings ORDER BY id'):
   l=loc_by_build.get(r['id'])
   dst.execute('INSERT INTO atlas_buildings(id,name,street,exterior_number,colony,city,state,postal_code,notes,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(r['id'],r['name'],(l['street'] if l else '') or '',(l['exterior_number'] if l else '') or '',(l['colony'] if l else '') or '',(l['city'] if l else '') or '',(l['state'] if l else '') or '',(l['postal_code'] if l else '') or '',r['notes'],r['created_at'],r['updated_at']))
  people={}
  def person(name,phone='',email=''):
   name=(name or '').strip()
   if not name:return None
   key=name.casefold()
   if key in people:return people[key]
   cur=dst.execute('INSERT OR IGNORE INTO atlas_people(full_name,phone,email) VALUES(?,?,?)',(name,phone or '',email or ''))
   row=dst.execute('SELECT id FROM atlas_people WHERE lower(trim(full_name))=lower(trim(?))',(name,)).fetchone(); people[key]=row[0]; return row[0]
  for r in src.execute('SELECT d.*,l.building_id,l.floor FROM dependencies d JOIN locations l ON l.id=d.location_id ORDER BY d.id'):
   dst.execute('INSERT INTO atlas_dependencies(id,building_id,name,court,tribunal,floor,phone,email,notes,active,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(r['id'],r['building_id'],r['name'],r['court'],r['tribunal'],r['floor'],r['phone'],r['email'],r['notes'],r['active'],r['created_at'],r['updated_at']))
   if (r['office'] or '').strip(): dst.execute('INSERT OR IGNORE INTO atlas_offices(dependency_id,name) VALUES(?,?)',(r['id'],r['office'].strip()))
   pid=person(r['cta'],r['phone'],r['email'])
   if pid: dst.execute("INSERT OR IGNORE INTO atlas_dependency_people VALUES(?,?,'CTA')",(r['id'],pid))
  eqcols={x['name'] for x in src.execute('pragma table_info(equipment)')}
  for r in src.execute('SELECT * FROM equipment ORDER BY id'):
   pid=person(r['assigned_user'] if 'assigned_user' in eqcols else '')
   dst.execute('INSERT INTO atlas_equipment(id,dependency_id,assigned_person_id,equipment_type,brand,model,serial_number,inventory_number,ip_address,hostname,status,notes,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(r['id'],r['dependency_id'],pid,r['equipment_type'],r['brand'],r['model'],r['serial_number'],r['inventory_number'],r['ip_address'],r['hostname'],r['status'],r['notes'],r['created_at'],r['updated_at']))
  for r in src.execute('SELECT * FROM counter_records ORDER BY id'):
   dst.execute('INSERT INTO atlas_counter_readings(id,external_uid,equipment_id,reading_date,serial_snapshot,model_snapshot,source_file,total_prints,office_prints,letter_prints,duplex_sheets,jam_events,misfeed_events,economode_prints,format_type,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',tuple(r[k] for k in ('id','record_uid','equipment_id','reading_date','serial_number','model','source_file','total_prints','office_prints','letter_prints','duplex_sheets','jam_events','misfeed_events','economode_prints','format_type','created_at','updated_at')))
  socols=[x['name'] for x in src.execute('pragma table_info(service_orders)') if x['name'] in {y['name'] for y in dst.execute('pragma table_info(atlas_service_orders)')}]
  for r in src.execute('SELECT * FROM service_orders ORDER BY id'): dst.execute(f"INSERT INTO atlas_service_orders({','.join(socols)}) VALUES({','.join('?' for _ in socols)})",tuple(r[x] for x in socols))
  if _table_exists(src,'service_formats'):
   cols=[x['name'] for x in src.execute('pragma table_info(service_formats)')]
   for r in src.execute('SELECT * FROM service_formats'): dst.execute(f"INSERT INTO service_formats({','.join(cols)}) VALUES({','.join('?' for _ in cols)})",tuple(r[x] for x in cols))
  for t in ('app_metadata','sync_metadata'):
   if _table_exists(src,t):
    for r in src.execute(f'SELECT * FROM {t}'):
     cols=r.keys(); dst.execute(f"INSERT OR REPLACE INTO {t}({','.join(cols)}) VALUES({','.join('?' for _ in cols)})",tuple(r[x] for x in cols))
  _seed(dst); dst.execute("UPDATE app_metadata SET value='3',updated_at=CURRENT_TIMESTAMP WHERE key='schema_version'")
  _ensure_clean_sync_records(dst)
  dst.executescript(VIEW_SCHEMA); dst.executescript(TRIGGERS); dst.commit()
  if dst.execute('pragma integrity_check').fetchone()[0]!='ok' or dst.execute('pragma foreign_key_check').fetchall(): raise RuntimeError('Clean database validation failed')
 finally: src.close(); dst.close()
