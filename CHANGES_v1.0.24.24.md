# CodeCafe Atlas v1.0.24.24

Build/reproducibility maintenance release based directly on the v1.0.24.23 candidate-stable functional baseline.

- No application workflow or database schema redesign.
- Adds `bootstrap_dependencies.py`, a persistent platform/Python-specific wheel/package cache under `packages/`.
- Reuses cached packages offline and only accesses the Internet when the matching cache is incomplete.
- Recreates an incompatible or damaged `.venv` automatically instead of relying on stale virtual environments from another Python installation.
- Runs dependency bootstrap before all validators, fixing the Windows clean-machine failure where `openpyxl` was imported before requirements were installed.
- Runs public-identity, cumulative full-functionality, and pre-build validators before accepting a build.
- Windows PyInstaller work and first startup smoke-test now occur under a local `%LOCALAPPDATA%` staging directory instead of directly in a synchronized/OneDrive source path.
- The tested Windows build is copied back to `dist/CodeCafe-Atlas` and a portable ZIP is generated in `release/`.
- Repeated builds safely recreate disposable `build`/`dist` outputs while preserving the dependency cache.
- Linux and macOS build entrypoints use the same dependency bootstrap/cache strategy.
- Version/build messages corrected to v1.0.24.24.

Known distribution rule: the Windows ZIP should be extracted before execution. A normal local, non-synchronized folder is the preferred runtime location; the build itself proves startup from a local staging path before it is accepted.

## Build guard correction (Linux test cycle)
- Corrected `validate_before_build.py` so the Windows `data/` and `backups/` requirement is validated across the real Windows build chain (`build_windows.bat` + `build_windows_release.py`).
- The Windows batch file intentionally delegates final distribution assembly to `build_windows_release.py`; the previous guard inspected only the batch text and incorrectly blocked Linux builds.
- Added a guard that confirms `build_windows.bat` actually invokes `build_windows_release.py`, preserving the regression protection rather than weakening it.
- No Atlas application/module/database behavior changed.

## Homologador — reparación auditada
- `Usar externo` ahora adopta también la identidad persistente (`record_uuid`) y la procedencia/revisión del registro externo.
- Las actualizaciones de registros con UUID compartido sincronizan `revision` y `updated_by_installation`.
- Los registros coincidentes refrescan metadatos de sincronización sin modificar sus datos de negocio.
- Un plan de homologación queda invalidado si la base local o la externa cambian después del análisis; Atlas exige volver a analizar antes de aplicar.
- El reporte de homologación identifica correctamente la versión 1.0.24.24.
- Se añadió `validate_homologator_runtime.py`, que prueba adopción de identidad, reanálisis sin duplicado recurrente, propagación de revisión y rechazo de planes obsoletos.
- No se cambió el esquema de base de datos ni la interfaz del homologador.

## Órdenes / Cédulas de Servicio — configuración flexible
- El Reporte DGTI es ahora la única captura del identificador: se guarda también como `folio` para conservar compatibilidad con la base existente.
- Se eliminó el campo visible redundante `Folio`; al abrir registros antiguos, DGTI usa el folio previo como respaldo cuando el campo DGTI histórico estaba vacío.
- La Cédula de Servicio usa el Reporte DGTI/folio como nombre base del archivo generado.
- El configurador permite añadir y eliminar filas y editar `Campo Atlas`, `Placeholder`, `Celda(s)` y `Requerido`.
- La condición `Requerido` queda persistida por plantilla activa, no fijada permanentemente por la interfaz.
- Los placeholders editados pueden actuar como alias de campos Atlas ya existentes, conservando su fuente de datos.
- La Cédula de Servicio depende exclusivamente de la plantilla activa administrada; ya no busca plantillas históricas por nombre.
- La plantilla incluida queda únicamente como recuperación explícita mediante `Restaurar plantilla incluida`.
- Se retiraron del paquete los archivos redundantes `Formato de referencia - Cédula de Servicio.xlsx` y `PLACEHOLDERS_CEDULA_SERVICIO.txt`.
- El libro maestro `Formato de referencia - Cédulas.xlsx` se conserva solamente para Mantenimiento Preventivo y Dictaminación, evitando regresiones en esos tipos de documento.
