# Homologation and Sync Internals

## Engine
`sync_engine.py`

`SyncEngine` compares a local canonical DB with an external DB prepared for comparison.

Important responsibilities:
- validate clean/canonical schema;
- build natural keys and stable identifiers;
- compare normalized payloads;
- classify differences;
- create a backup before applying changes;
- translate external IDs to local IDs;
- preserve/update sync UUID identity;
- apply changes transactionally;
- produce a report.

## UI
`sync_compare_page.py`

`SyncComparePage` handles:
- selecting external DB;
- compare/analyze;
- presenting plan;
- homologating;
- exporting comparison results.

## Safety boundary

The external source DB is not the write target. Legacy/external preparation should occur on temporary copies. Local changes require backup and transaction protection.

## Why sync identity exists

Natural business identifiers may change. `atlas_sync_records` provides a persistent record UUID and revision/provenance layer so homologation does not rely only on mutable names.
