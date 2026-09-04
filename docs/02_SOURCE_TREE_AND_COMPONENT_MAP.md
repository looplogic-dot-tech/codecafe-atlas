# Source Tree and Component Map

## Repository root

- `CHANGES_v1.0.24.16.md`
- `CHANGES_v1.0.24.17.md`
- `CHANGES_v1.0.24.18.md`
- `CHANGES_v1.0.24.19.md`
- `CHANGES_v1.0.24.20.md`
- `CHANGES_v1.0.24.21.md`
- `CHANGES_v1.0.24.22.md`
- `CHANGES_v1.0.24.23.md`
- `CLEANUP_VALIDATION_REPORT.txt`
- `CODECAFE_ATLAS_IDENTITY.json`
- `FULL_FUNCTION_VALIDATION_REPORT.txt`
- `PUBLIC_SOURCE_NOTES.md`
- `README.md`
- `RECOVERY_AUDIT_v1.0.24.17.md`
- `REGRESSION_REPORT_v1.0.24.19.txt`
- `REGRESSION_REPORT_v1.0.24.20.txt`
- `REGRESSION_REPORT_v1.0.24.21.txt`
- `SOURCE_FILE_HASHES_SHA256.txt`
- `__pycache__/` — 6 files
- `assets/` — 3 files
- `backups/` — 1 files
- `build_linux.sh`
- `build_macos.sh`
- `build_windows.bat`
- `codecafe_atlas/` — 62 files
- `codecafe_atlas_updater.py`
- `data/` — 1 files
- `main.py`
- `make_update_package.py`
- `modules/` — 9 files
- `requirements.txt`
- `run_linux.sh`
- `run_windows.bat`
- `validate_before_build.py`
- `validate_full_functionality.py`
- `validate_public_identity.py`

## Python package responsibilities

- `main_window.py` — application shell, navigation, page wiring, startup and shutdown behavior.
- `database.py` — principal operational data API and database administration interface.
- `clean_database.py` — canonical SQLite schema, compatibility views/triggers, initialization and legacy migration.
- `paths.py` — runtime roots, asset/data/backups paths and controlled same-installation DB adoption.
- `directory_page.py` — building/dependency-centered UI.
- `inventory_page.py` — equipment-centered UI, sorting and duplicate workflow.
- `data_page.py` — import/preview/reset/backup/export administration.
- `counter_registry_page.py` — bridge between the counter UI and SQLite/OCR/export services.
- `counter_inserter_engine.py` — spreadsheet analysis and controlled counter insertion engine.
- `counter_inserter_page.py` — Qt wrapper for the insertion engine.
- `pdf_page.py` — PDF Separator processing/review/export.
- `pdf_library_page.py` — PDF Viewer/library and duplicate handling.
- `pdf_duplicate_tools.py` — content hashing/duplicate detection support.
- `service_order_page.py` — operational service-document workflow.
- `service_document_generator.py` — Excel-template document generation.
- `service_template_config.py` — first-run/custom-template mapping configuration.
- `formats_page.py` — reusable format/template library UI.
- `sync_engine.py` — homologation planning and apply engine.
- `sync_compare_page.py` — homologation UI.
- `updater.py` / `update_dialog.py` — update package inspection/launch.
- `codecafe_atlas_updater.py` — external replacement/updater executable.
- `platform_open.py` — system file-manager launching with PyInstaller-safe environment.
- `identity.py` — product identity constants.
- `ui_helpers.py` — shared UI construction helpers.

## Runtime-owned directories

- `data/` — writable state and active database.
- `backups/` — SQLite backups.
- `modules/` — runtime-editable module/template assets copied from bundle when needed.
- `assets/` — packaged icons/logo.
