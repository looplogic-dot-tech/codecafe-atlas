# CodeCafe Atlas v1.0.24.46

## Historial de contadores editable y advertencia de series

- Añade el botón `Editar` a cada lectura histórica guardada.
- Permite corregir fecha, número de serie, modelo, archivo de origen y contadores.
- Una serie corregida con coincidencia exacta se vincula nuevamente al equipo de Inventario.
- Detecta series no registradas a una sola edición de distancia de una serie existente.
- La similitud es únicamente una advertencia: Atlas nunca sustituye ni crea automáticamente sin confirmación.
- Conserva valores anteriores y posteriores de cada edición en `atlas_counter_reading_edits`.
- Validado con el caso real `VNB00B01235` → `VNB0B01235` sobre una copia de la base.

## Alcance

Esta versión corrige el origen histórico dentro de Atlas. La misma regla deberá integrarse al Data Recovery Tool cuando su fuente esté disponible.
