# CodeCafe Atlas v1.0.24.25

Production follow-up release based on v1.0.24.24.

- Service Order: registered equipment now remains the source of truth for its serial field; selecting equipment populates the serial automatically.
- Service Order: an exact registered serial can be entered before choosing a dependency; Atlas selects the equipment's dependency and equipment automatically.
- Service Order: removed the redundant visible "Datos predefinidos / Precargar datos" bar to reduce UI clutter. Template loading remains in "Cargar / configurar plantilla Excel".
- Preserves v1.0.24.24 counter shared-history fix, homologator identity/revision repair, configurable single active service template, Linux native file opening, Windows pip recovery and isolated PyInstaller path fixes.
- No database schema change.
- UI completion: removed the visible active-template path and the automatic "Datos actualizados" status line marked for removal; no saved-format selector/preload controls remain in Service Order.
- Preserved Administración de formatos -> Usar en orden de servicio as a backend action without depending on the removed selector widget.

## Startup correction after preset-UI removal
- Removed the obsolete `FormatsPage.formats_changed -> ServiceOrderPage.refresh_saved_formats` signal connection.
- The service-order preset selector was intentionally removed, so `refresh_saved_formats()` no longer exists.
- `Administración de formatos -> Usar en orden de servicio` remains available through `format_requested -> apply_service_format()`.
- Added a regression guard preventing startup wiring from referencing the removed method again.

## Service Order complete reset
- `Nuevo / limpiar` now resets the entire service-order form: document values, output path, dependency search/selection and derived data, equipment search/selection and derived data, responsible/validator fields, service fields, dates/times and mode defaults.
- Template configuration and history are intentionally preserved because they are application state, not fields belonging to the current order.
- Added a cumulative regression guard that verifies the complete reset contract.
