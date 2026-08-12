# CodeCafe Atlas v1.0.24.17 — Consolidación de recuperación

- Parte directamente de v1.0.24.16 Public Clean Source.
- Administración de formatos funciona como biblioteca: el panel de detalle permanece neutro hasta seleccionar un formato o pulsar Nuevo formato.
- La lista principal deja de mostrar Movimiento como columna global; los detalles específicos aparecen únicamente dentro del formato seleccionado.
- Se restaura/refuerza la política de no duplicados organizacionales para edificios y dependencias.
- Coincidencias equivalentes se bloquean incluso con diferencias de acentos, puntuación, orden de palabras y numeración común.
- Coincidencias cercanas generan una advertencia y requieren confirmación explícita; Atlas nunca fusiona automáticamente.
- No se modifica el esquema SQLite.
- Se conservan las funciones de v1.0.24.16: plantilla inicial configurable, plantilla XLSX propia, hoja seleccionable y mapeo campo→celda/placeholders.
