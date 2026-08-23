# Counter shared-history production fix — v1.0.24.24

Production issue observed 2026-08-17: saving from **Contador de impresiones** failed with SQLite `cannot UPSERT a view`.

Root cause: `save_equipment_counter()` and `save_counter_records()` used `INSERT ... ON CONFLICT` against compatibility view `counter_records`. SQLite cannot apply UPSERT to a view.

Correction: both write/update paths now target canonical table `atlas_counter_readings` using its canonical column names (`external_uid`, `serial_snapshot`, `model_snapshot`). Compatibility view `counter_records` and its triggers remain intact for compatibility/read/delete paths. No schema change or migration is required.

Regression protection: `validate_before_build.py` now creates a temporary clean database, writes and updates the same reading through both counter APIs, verifies one shared history record and confirms it resides in `atlas_counter_readings`.

Verified in source environment:
- `validate_before_build.py`: PASS, including COUNTER SHARED HISTORY VALIDATION
- `validate_full_functionality.py`: PASS
- `validate_public_identity.py`: PASS / zero forbidden-name occurrences
- direct shared counter write/update integration test: PASS

Production GUI verification remains required after building: save/edit from Contador de impresiones, confirm in Registro de contadores, then save/update from Registro de contadores and confirm the same history from the equipment dialog.
