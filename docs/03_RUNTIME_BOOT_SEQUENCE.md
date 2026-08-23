# Runtime Boot Sequence

## Entry point

`main.py` imports `run` from `codecafe_atlas.main_window` and exits with its return code.

## Application root resolution

`paths.application_root()` behaves differently by runtime:

- source mode: repository root;
- PyInstaller/frozen mode: directory containing the executable.

`paths.bundled_root()` uses `sys._MEIPASS` when PyInstaller has extracted bundled resources.

## Database path resolution

`paths.database_path()` resolves to:

`<application_root>/data/atlas.db`

Before returning the path, Atlas may adopt a recognized database from the **same installation's `data/` directory** only when `atlas.db` does not already contain data.

It does not scan sibling version directories.

## Database initialization

`Database.__init__()` calls `initialize()`, which delegates canonical/legacy handling to `ensure_clean_database()`.

Initialization cases:

1. missing/zero-byte DB -> create canonical schema;
2. canonical schema -> verify/complete sync identity;
3. recognized legacy schema -> create backup and migrate;
4. unknown/partial schema -> reject without modifying it.

## Main window

The MainWindow constructs the shared `Database` instance and page objects. Pages therefore operate on the same active DB.

## Shutdown

Normal shutdown includes backup behavior. The backup directory is application-local and separate from `data/`.
