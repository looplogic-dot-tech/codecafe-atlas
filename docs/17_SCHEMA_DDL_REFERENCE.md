# SQLite Schema DDL Reference

Extracted from `codecafe_atlas/clean_database.py` in v1.0.24.23.

## Canonical tables

### `atlas_buildings`

```sql
CREATE TABLE atlas_buildings(id INTEGER PRIMARY KEY AUTOINCREMENT,
 name TEXT NOT NULL COLLATE NOCASE UNIQUE,
 street TEXT NOT NULL DEFAULT '', exterior_number TEXT NOT NULL DEFAULT '', colony TEXT NOT NULL DEFAULT '',
 city TEXT NOT NULL DEFAULT '', state TEXT NOT NULL DEFAULT '', postal_code TEXT NOT NULL DEFAULT '',
 country TEXT NOT NULL DEFAULT 'México', notes TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
```

### `atlas_people`

```sql
CREATE TABLE atlas_people(id INTEGER PRIMARY KEY AUTOINCREMENT,
 full_name TEXT NOT NULL COLLATE NOCASE,
 phone TEXT NOT NULL DEFAULT '', email TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
```

### `atlas_dependencies`

```sql
CREATE TABLE atlas_dependencies(id INTEGER PRIMARY KEY AUTOINCREMENT,
 building_id INTEGER NOT NULL REFERENCES atlas_buildings(id) ON DELETE RESTRICT,
 name TEXT NOT NULL COLLATE NOCASE, court TEXT NOT NULL DEFAULT '', tribunal TEXT NOT NULL DEFAULT '',
 floor TEXT NOT NULL DEFAULT '', phone TEXT NOT NULL DEFAULT '', email TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '',
 active INTEGER NOT NULL DEFAULT 1 CHECK(active IN(0,1)),
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(building_id,name,floor));
```

### `atlas_offices`

```sql
CREATE TABLE atlas_offices(id INTEGER PRIMARY KEY AUTOINCREMENT,
 dependency_id INTEGER NOT NULL REFERENCES atlas_dependencies(id) ON DELETE CASCADE,
 name TEXT NOT NULL COLLATE NOCASE, notes TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(dependency_id,name));
```

### `atlas_dependency_people`

```sql
CREATE TABLE atlas_dependency_people(dependency_id INTEGER NOT NULL REFERENCES atlas_dependencies(id) ON DELETE CASCADE,
 person_id INTEGER NOT NULL REFERENCES atlas_people(id) ON DELETE RESTRICT,
 role TEXT NOT NULL COLLATE NOCASE,
 PRIMARY KEY(dependency_id,person_id,role));
```

### `atlas_equipment`

```sql
CREATE TABLE atlas_equipment(id INTEGER PRIMARY KEY AUTOINCREMENT,
 dependency_id INTEGER NOT NULL REFERENCES atlas_dependencies(id) ON DELETE RESTRICT,
 office_id INTEGER REFERENCES atlas_offices(id) ON DELETE SET NULL,
 assigned_person_id INTEGER REFERENCES atlas_people(id) ON DELETE SET NULL,
 equipment_type TEXT NOT NULL DEFAULT '', brand TEXT NOT NULL DEFAULT '', model TEXT NOT NULL DEFAULT '',
 serial_number TEXT NOT NULL DEFAULT '', inventory_number TEXT NOT NULL DEFAULT '', ip_address TEXT NOT NULL DEFAULT '',
 hostname TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'Activo', notes TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
```

### `atlas_counter_readings`

```sql
CREATE TABLE atlas_counter_readings(id INTEGER PRIMARY KEY AUTOINCREMENT, external_uid TEXT NOT NULL UNIQUE,
 equipment_id INTEGER REFERENCES atlas_equipment(id) ON DELETE SET NULL,
 reading_date TEXT NOT NULL DEFAULT '', serial_snapshot TEXT NOT NULL DEFAULT '', model_snapshot TEXT NOT NULL DEFAULT '',
 source_file TEXT NOT NULL DEFAULT '', total_prints REAL, office_prints REAL, letter_prints REAL, duplex_sheets REAL,
 jam_events REAL, misfeed_events REAL, economode_prints REAL, format_type TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
```

### `atlas_service_orders`

```sql
CREATE TABLE atlas_service_orders(id INTEGER PRIMARY KEY AUTOINCREMENT, folio TEXT NOT NULL DEFAULT '', document_type TEXT NOT NULL DEFAULT 'Cédula de Servicio',
 equipment_id INTEGER REFERENCES atlas_equipment(id) ON DELETE SET NULL,
 dependency_id INTEGER REFERENCES atlas_dependencies(id) ON DELETE SET NULL,
 dgti_report TEXT NOT NULL DEFAULT '', provider_report TEXT NOT NULL DEFAULT '', report_date TEXT NOT NULL DEFAULT '', report_time TEXT NOT NULL DEFAULT '',
 responsible_name TEXT NOT NULL DEFAULT '', validator_name TEXT NOT NULL DEFAULT '', validator_role TEXT NOT NULL DEFAULT '', validator_phone TEXT NOT NULL DEFAULT '',
 movement_type TEXT NOT NULL DEFAULT '', reported_issue TEXT NOT NULL DEFAULT '', diagnosis TEXT NOT NULL DEFAULT '', diagnosis_date TEXT NOT NULL DEFAULT '', diagnosis_time TEXT NOT NULL DEFAULT '',
 solution TEXT NOT NULL DEFAULT '', solution_date TEXT NOT NULL DEFAULT '', solution_time TEXT NOT NULL DEFAULT '', service_notes TEXT NOT NULL DEFAULT '', technician_name TEXT NOT NULL DEFAULT '',
 equipment_operates TEXT NOT NULL DEFAULT '', equipment_condition TEXT NOT NULL DEFAULT '', output_path TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
```

### `service_formats`

```sql
CREATE TABLE service_formats(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL COLLATE NOCASE UNIQUE, document_type TEXT NOT NULL DEFAULT 'Cédula de Servicio',
 description TEXT NOT NULL DEFAULT '', validator_name TEXT NOT NULL DEFAULT '', validator_role TEXT NOT NULL DEFAULT '', validator_phone TEXT NOT NULL DEFAULT '',
 movement_type TEXT NOT NULL DEFAULT '', reported_issue TEXT NOT NULL DEFAULT '', diagnosis TEXT NOT NULL DEFAULT '', solution TEXT NOT NULL DEFAULT '', service_notes TEXT NOT NULL DEFAULT '',
 technician_name TEXT NOT NULL DEFAULT '', equipment_operates TEXT NOT NULL DEFAULT 'Sí', equipment_condition TEXT NOT NULL DEFAULT 'No', active INTEGER NOT NULL DEFAULT 1,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
```

### `app_metadata`

```sql
CREATE TABLE app_metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL DEFAULT '',updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
```

### `sync_metadata`

```sql
CREATE TABLE sync_metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
```

### `atlas_sync_records`

```sql
CREATE TABLE atlas_sync_records(entity_type TEXT NOT NULL, entity_id INTEGER NOT NULL, record_uuid TEXT NOT NULL UNIQUE,
 revision INTEGER NOT NULL DEFAULT 1, created_by_installation TEXT NOT NULL DEFAULT '', updated_by_installation TEXT NOT NULL DEFAULT '', deleted_at TEXT,
 PRIMARY KEY(entity_type,entity_id));
```

### `atlas_location_input`

```sql
CREATE TABLE atlas_location_input(id INTEGER PRIMARY KEY AUTOINCREMENT, building_id INTEGER, building TEXT NOT NULL DEFAULT '', city TEXT NOT NULL DEFAULT '', state TEXT NOT NULL DEFAULT '',
 street TEXT NOT NULL DEFAULT '', exterior_number TEXT NOT NULL DEFAULT '', colony TEXT NOT NULL DEFAULT '', postal_code TEXT NOT NULL DEFAULT '', floor TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
```

## Indexes

- `uq_atlas_people_name` on `atlas_people`: `lower(trim(full_name))`
- `uq_atlas_equipment_serial` on `atlas_equipment`: `lower(trim(serial_number))`; partial condition: `trim(serial_number)<>''`
- `uq_atlas_equipment_inventory` on `atlas_equipment`: `lower(trim(inventory_number))`; partial condition: `trim(inventory_number)<>''`
- `uq_atlas_equipment_hostname` on `atlas_equipment`: `lower(trim(hostname))`; partial condition: `trim(hostname)<>''`
- `idx_atlas_equipment_dependency` on `atlas_equipment`: `dependency_id`
- `idx_atlas_counter_equipment_date` on `atlas_counter_readings`: `equipment_id,reading_date DESC,id DESC`

## Compatibility views

- `buildings`
- `locations`
- `dependencies`
- `equipment`
- `counter_records`
- `service_orders`

## Compatibility triggers

- `buildings_insert`
- `buildings_update`
- `buildings_delete`
- `locations_insert`
- `locations_update`
- `locations_delete`
- `dependencies_insert`
- `dependencies_update`
- `dependencies_delete`
- `equipment_insert`
- `equipment_update`
- `equipment_delete`
- `counter_insert`
- `counter_update`
- `counter_delete`
- `service_orders_insert`
- `service_orders_update`
- `service_orders_delete`
