# Reproducibility Runbook

## Objective

Reconstruct CodeCafe Atlas v1.0.24.23 from source without relying on chat history.

## Reference integrity

Reference source archive SHA-256:

`3bf57b88cd0cd417116ba30291a3ceda9978d5cf6905e13c2c3668bd2bff36de`

Verify first:

```bash
sha256sum CodeCafe_Atlas_v1.0.24.23_FULL_FUNCTION_RECOVERY_SOURCE.zip
```

## Linux reconstruction

Prerequisites:
- Python 3
- venv support
- a C/C++ runtime suitable for binary wheels
- Tesseract OCR for native OCR use

Procedure:

```bash
unzip CodeCafe_Atlas_v1.0.24.23_FULL_FUNCTION_RECOVERY_SOURCE.zip
cd CodeCafe_Atlas_v1.0.24.23_FULL_FUNCTION_RECOVERY_SOURCE
python3 validate_before_build.py
python3 validate_public_identity.py
./build_linux.sh
```

Expected output directory:

```text
dist/CodeCafe-Atlas/
  CodeCafe-Atlas
  CodeCafe-Atlas-Updater
  CODECAFE_ATLAS_IDENTITY.json
  data/
  backups/
  modules/
  assets/
  ...PyInstaller runtime files...
```

## First run

A clean distribution contains no operational DB. Atlas creates `data/atlas.db` on first run.

Expected new DB:
- canonical schema version 3;
- valid installation UUID;
- no production buildings/dependencies/equipment/counters/orders/formats;
- `PRAGMA integrity_check = ok`;
- no FK violations.

## Restoring existing data

Do not copy arbitrary SQLite files over `atlas.db`.

Use the application's import/preview/replacement path, or place only a recognized compatible DB intentionally in the same installation's `data/` directory before first authoritative `atlas.db` creation.

Unknown DB schemas must be rejected, not guessed.

## Verification after reconstruction

1. app starts;
2. Directory and Inventory show the same canonical equipment population;
3. create/edit building and dependency;
4. duplicate/similar building warning works;
5. equipment edit persists;
6. duplicate review works;
7. Data Administration preview/import works on a copy;
8. counter modules open;
9. PDF Separator opens and processes a safe test PDF;
10. Service Orders opens and template configuration loads;
11. folder-opening buttons launch the desktop file manager;
12. Homologation compares safe DB copies;
13. normal exit creates backup.

## Archival set

Keep together:
- exact source ZIP;
- SHA-256;
- this `docs/` directory;
- release/change notes;
- a sanitized synthetic test fixture set;
- build environment notes.
