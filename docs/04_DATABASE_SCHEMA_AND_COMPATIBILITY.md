# Database Schema and Compatibility

## Active database

`data/atlas.db`

SQLite foreign keys are enabled by the canonical schema.

## Canonical schema version

`CLEAN_SCHEMA_VERSION = "3"`

The schema is defined directly in `codecafe_atlas/clean_database.py`.

## Canonical entities

### `atlas_buildings`
Owns building identity and structured address.

### `atlas_people`
Stores people such as CTAs/responsible users.

### `atlas_dependencies`
Belongs to one building. Owns floor, contact and organizational notes.

Compatibility columns `court` and `tribunal` remain in the schema for historical compatibility; the current UI does not require them as separate business concepts.

### `atlas_offices`
Optional subdivision of one dependency.

### `atlas_dependency_people`
Many-to-many dependency/person roles.

### `atlas_equipment`
Authoritative equipment record. Directory and Inventory both consume this entity.

Important duplicate-sensitive identifiers have partial unique indexes when nonblank:
- serial number
- inventory number
- hostname

### `atlas_counter_readings`
Historical readings with equipment link plus snapshots of serial/model/source values.

### `atlas_service_orders`
Operational service-document records.

### `service_formats`
Reusable format presets/templates used by document workflows.

### `atlas_sync_records`
Stable UUID/revision identity for homologation.

### `app_metadata`, `sync_metadata`
Application/database identity and synchronization metadata.

## Compatibility layer

The canonical DB deliberately exposes compatibility views and INSTEAD OF triggers for older SQL-facing module behavior. These views are adapters, not authoritative storage.

Do not redesign/remove a compatibility view merely because the canonical table appears cleaner. First find every consumer.

## Legacy migration

A legacy DB is recognized only if it contains the complete required legacy table set, including `buildings`, `locations`, `dependencies` and `equipment`.

Migration:

1. copy legacy DB to a timestamped backup;
2. create a temporary canonical DB;
3. migrate buildings/address data;
4. migrate dependency/CTA relationships;
5. migrate equipment;
6. migrate counter history;
7. migrate service orders and formats when present;
8. seed application metadata;
9. create sync identities;
10. install compatibility views/triggers;
11. run SQLite integrity and FK validation;
12. atomically replace the active DB.

Unknown schemas are rejected instead of guessed.

## Sync identity

Each supported entity receives a stable `record_uuid`, revision and installation provenance. The installation UUID is stored in `sync_metadata`.
