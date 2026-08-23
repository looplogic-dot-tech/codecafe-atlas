# Build, Packaging and Updater

## Dependencies
See `requirements.txt`.

## Linux source run

```bash
./run_linux.sh
```

The script creates `.venv` when missing, installs requirements and runs `main.py`.

## Linux build

```bash
./build_linux.sh
```

Build flow:
1. `validate_before_build.py`
2. `validate_public_identity.py`
3. create/reuse `.venv`
4. install requirements
5. remove old `build/` and `dist/`
6. PyInstaller onedir app `CodeCafe-Atlas`
7. PyInstaller onefile updater `CodeCafe-Atlas-Updater`
8. copy updater into final app directory
9. create empty `data/` and `backups/`
10. copy identity JSON
11. set executable permissions
12. run offscreen smoke-start with timeout
13. fail on traceback/AttributeError/PyInstaller launch error

## Windows build

`build_windows.bat` mirrors the same structure with Windows path syntax and `.exe` output.

## macOS

`build_macos.sh` exists and produces an onedir build. This source documents a target, not a claim of equivalent production validation.

## Update package

`make_update_package.py` creates a ZIP containing:
- `update_manifest.json`
- `payload/`
- SHA-256 metadata
- file modes/executable metadata where relevant

## External updater

`codecafe_atlas_updater.py`:
- waits for main process exit;
- safely extracts package (path traversal checks);
- validates payload root;
- stages the new installation;
- preserves `data` and `backups`;
- renames current install to timestamped backup;
- installs staging;
- rolls back if replacement fails;
- restores executable permissions;
- optionally restarts Atlas.

This updater is intentionally separate from the main process so the running application can be replaced safely.
