# Service Order follow-up fix — v1.0.24.24

## Production observations addressed

1. Generated XLSX files could be opened from Atlas on Windows but not from the frozen Linux build.
2. The UI wording around “Formato guardado / Precargar formato” was easy to confuse with loading the active Excel template.

## Correction

- Added `open_file_native()` in `codecafe_atlas/platform_open.py`. It launches files through KDE/GNOME native helpers using the same PyInstaller-safe environment already proven for folder opening, with LibreOffice as a final Linux fallback for spreadsheet files.
- Both “Abrirlo ahora” after generation and “Abrir archivo seleccionado” in history use this native launcher and report diagnostics instead of failing silently.
- Clarified the service-order UI:
  - `Cargar / configurar plantilla Excel` manages the actual XLSX template.
  - `Datos predefinidos / Precargar datos` only loads reusable service-order field values from `service_formats`; it does not replace the Excel template.
- The custom-template button now explicitly says `Cargar plantilla Excel propia…`.

No database schema or homologator/counter behavior was changed.
