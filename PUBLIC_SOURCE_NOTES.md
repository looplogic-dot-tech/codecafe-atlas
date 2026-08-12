# CodeCafe Atlas v1.0.24.16 — Public clean source

This source package is derived directly from the archived v1.0.24.16 source and preserves the desktop application architecture and database schema.

No operational SQLite database or historical database backup is distributed. Atlas creates `data/atlas.db` on first run. Existing compatible Atlas databases can still be selected through **Administrar datos**, and a compatible database placed in the local `data/` directory can be adopted automatically when the active database is empty.

Historical release reports are kept in the private project archive rather than this public source tree because they may contain operational examples.

## Clean-database and service-order UI correction

- A brand-new local database no longer receives starter service-format rows; its operational tables begin empty.
- Existing compatible Atlas databases retain their existing service formats and are not altered by this change.
- The service-order **Actualizar datos** action now gives visible non-modal feedback with refreshed dependency/equipment counts.
- **Buscar / abrir carpeta** now uses the native platform file-manager opener first, with Qt as a fallback.
