# CodeCafe Atlas v1.0.24.40

## Series discrepantes editables

- Las filas con discrepancias de número de serie permiten editar la primera columna mediante doble clic o `F2`.
- También se incorpora el botón `Corregir serie seleccionada…` para hacer explícita la acción.
- Atlas normaliza la corrección, vuelve a leer las fuentes y repite el análisis completo.
- La nueva escritura solo se acepta cuando produce una coincidencia exacta o una alta que cumpla las reglas existentes.
- Una serie ya corregida puede editarse nuevamente o devolverse a su valor original.

## Seguridad de datos

- La corrección modifica únicamente la interpretación del lote actual.
- No altera automáticamente la serie histórica almacenada en `atlas.db`.
- La hoja maestra original continúa protegida; solamente se genera una copia después de la confirmación habitual.
