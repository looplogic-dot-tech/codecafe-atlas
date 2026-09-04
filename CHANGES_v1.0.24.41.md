# CodeCafe Atlas v1.0.24.41

## Ubicación de Equipo desde la base de Atlas

- El Insertador puede completar `Ubicación de Equipo` usando la dependencia asociada a cada número de serie en `atlas.db`.
- La columna se detecta por encabezado y no queda amarrada permanentemente a `P`.
- La función está desactivada por omisión.
- El modo inicial llena únicamente celdas vacías.
- La opción secundaria autoriza reemplazar valores existentes que sean diferentes.
- La vista previa añade la ubicación existente, la dependencia de Atlas y la acción propuesta.

## Protecciones

- Si el encabezado de ubicación no existe, Atlas cancela el análisis antes de escribir.
- Las celdas con fórmulas permanecen protegidas.
- Dependencias ausentes no producen valores inventados.
- Dependencias distintas entre varias fuentes se bloquean como discrepancia.
- Todo reemplazo de ubicación se documenta en el CSV adicional.
- La copia generada se vuelve a abrir y se verifica celda por celda.
