# Failure Recovery and Troubleshooting

## App fails during DB initialization

Inspect:
- `data/atlas.db` existence/size;
- schema classification;
- whether the file is canonical, recognized legacy, or unknown.

Unknown/partial SQLite files should not be modified automatically.

## Directory and Inventory totals disagree

This is a regression signal. Both must represent canonical `atlas_equipment`. Look for joins through compatibility views that multiply rows, especially dependency/person relationships.

## Folder-open button does nothing in frozen build

Use `platform_open.py`. PyInstaller may alter library environment variables; external desktop applications must not inherit Atlas's private Qt/library search path.

## Build fails on permissions / `__pycache__`

Do not build with `sudo`. Remove root-owned build caches or restore ownership and rebuild as the normal user.

## Template fails validation

Run `validate_service_template()` and inspect:
- missing required placeholders;
- unknown placeholders;
- selected worksheet;
- direct cell map.

## Database import

Always preview before replacement. Keep the automatic backup. Never manually overwrite the live DB with an unverified file.

## Updater failure

The updater stages the new build and renames the existing install to a timestamped backup. If installation replacement fails, it attempts to restore the previous installation.

## Recovery principle

Do not solve a module bug by rebuilding the entire application from an arbitrary older source. Patch the current baseline and prove the regression scope.
