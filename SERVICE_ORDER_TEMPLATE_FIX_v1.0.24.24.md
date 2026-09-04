# Service Order / Cédula corrections — v1.0.24.24

- Reporte DGTI is the single user-entered identifier and is persisted as `folio`.
- The visible Folio field was removed from the form. Existing records fall back from legacy folio to DGTI when loaded.
- New Cédula de Servicio filenames use the DGTI/folio as the base filename.
- The template configurator now allows adding/removing mapping rows and editing Campo Atlas, Placeholder, Celda(s), and Requerido.
- Required mappings persist per active template instead of being permanently hard-coded in the dialog.
- Cédula generation uses only the explicitly configured active template and no longer falls back to historical filenames.
- The included default template remains only as an explicit recovery option.
- The legacy multi-sheet workbook remains only for Mantenimiento Preventivo / Dictaminación compatibility.
