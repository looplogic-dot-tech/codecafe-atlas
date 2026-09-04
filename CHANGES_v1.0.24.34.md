# CodeCafe Atlas v1.0.24.34

## Insertador inteligente de contadores

- Sustituye el destino mensual fijo por un bloque seleccionable de ocho columnas consecutivas.
- Conserva `AK:AR` como valor inicial para no alterar el flujo actual.
- Permite escribir solo la primera columna y calcula automáticamente las siete siguientes.
- Rechaza rangos incompletos, invertidos o con más/menos de ocho columnas.
- La detección estructural, lectura de valores, vista previa, escritura y verificación usan el mismo rango configurado.
- Mantiene protegidas las fórmulas y todas las columnas fuera del bloque elegido.
- No modifica la hoja maestra original: genera una copia nueva como antes.
