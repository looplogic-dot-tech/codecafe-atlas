# Configuration and State Files

## SQLite
`data/atlas.db` — operational database.

## Service-order settings
The Service Order page persists the last output directory in local data settings.

## Template configuration
`data/service_template_config.json` — custom/included template choice, worksheet and cell mapping.

Managed template content is stored under the service-template runtime/module area when configured.

## Dashboard
Dashboard personalization is stored locally under `data/dashboard/`.

## PDF Separator history
Stored as local metadata in `data/` through `separator_history.py`.

## Application/module resources
`paths.module_dir(name)` copies bundled module resources to an editable runtime `modules/<name>/` location when necessary.

## Backups
`backups/` contains timestamped SQLite backups and is preserved by the updater.

## Rule

Files under `data/` and `backups/` are runtime state and must not be committed as public operational data.
