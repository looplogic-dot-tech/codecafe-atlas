# CodeCafe Atlas v1.0.24.17 — Recovery audit (first consolidation pass)

## Source lineage actually compared

This candidate was built from the preserved `v1.0.24.16_PUBLIC_CLEAN_SOURCE` tree and compared against preserved source packages for:

- v1.0.22
- v1.0.23
- v1.0.24
- v1.0.24.1
- v1.0.24.3 through v1.0.24.15
- v1.0.24.16

Historical `CHANGES_*` and regression records included in the preserved trees were also used to verify intended behavior.

## Confirmed regression recovered in this pass

The clean-database rewrite removed the old database-level organizational duplicate helper used by v1.0.23. The later clean schema still had SQL uniqueness constraints, but it no longer enforced the user's broader duplicate policy for alternate punctuation/wording/numbering.

v1.0.24.17 restores and strengthens this protection without changing the SQLite schema:

- equivalent building names are blocked;
- equivalent dependency names in the same building are blocked;
- accents, punctuation, common ordinal/cardinal wording and word order are normalized for equivalence;
- near matches are shown to the user and require explicit confirmation;
- similar records are never silently merged.

## Recent v1.0.24.x functions verified present

- Inventory edits persist.
- Duplicate serial review exists.
- Duplicate review can continue across remaining groups.
- Inventory row-number column and total count exist.
- Inventory column sorting and natural serial sorting exist.
- Editable Excel export exists.
- Reset-to-empty exists.
- Database import preview and duplicate filtering exist.
- Building is the authoritative address owner and dependency address inheritance remains.
- PDF Separator continuous `Eliminar entrada` workflow remains.
- Counter Registry common metadata includes Zona / Dependencia / Notas / Mes.
- Clean-schema homologation engine remains.
- First-run configurable service template from v1.0.24.16 remains.
- Custom XLSX selection, sheet selection and field-to-cell / placeholder mapping remain.

## Administration de formatos correction

The existing `service_formats` schema and service-order integration are preserved for compatibility. The UI is now library-first:

- no service-order-specific editor is shown until the user selects a stored format;
- a neutral library message is displayed with no selection;
- `Nuevo formato` explicitly opens the editor;
- format details appear only after selection;
- the main library list is reduced to Name / Type / State / Updated.

This is intentionally an interface correction only; no SQLite schema migration was introduced.

## Database compatibility test actually performed

A copy of the active database included with the preserved original v1.0.24.15 source was opened by the consolidated implementation.

Before and after counts were identical:

- Buildings: 6
- Dependencies: 26
- Offices: 0
- People: 14
- Equipment: 103
- Counter readings: 85
- Service orders: 1
- Service formats: 3

`PRAGMA integrity_check = ok` and `PRAGMA foreign_key_check` returned zero rows before and after.

## Validation actually performed

- Python syntax compilation: 35 files — PASS.
- Project `validate_before_build.py` — PASS.
- `validate_public_identity.py` — ZERO forbidden legacy-name occurrences.
- New-building exact/equivalent duplicate test — PASS.
- Dependency near-duplicate detection test — PASS.
- Reordered/equivalent dependency duplicate block test — PASS.
- Existing v1.0.24.15 database compatibility/count/integrity test — PASS.

## Not tested in this environment

PySide6 is not installed in the execution environment, so a real GUI click-through or packaged Linux/Windows executable launch was not performed here. The user must compile and perform the final visual/operational acceptance test.
