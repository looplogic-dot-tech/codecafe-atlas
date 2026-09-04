# CodeCafe Atlas v1.0.24.43

## Corrección de ubicación durante la inserción

- La dependencia se obtiene de todos los equipos de `atlas_equipment`, no solamente de aquellos presentes en `atlas_counter_readings`.
- Los equipos registrados sin lectura histórica participan únicamente en la actualización de ubicación.
- La ausencia de lectura nunca se convierte en cero ni produce una alta automática en la hoja maestra.
- En modo reemplazo se exige coincidencia textual exacta con la dependencia canónica de Atlas; se corrigen abreviaturas y redacciones diferentes.
- Se conserva el mapeo de contadores `R,S,V,W` y la columna `P` permanece reservada para `Ubicación de Equipo`.

## Validación con datos operativos suministrados

- 200 lecturas históricas y 261 equipos registrados en la base.
- 264 series fuente al conservar también lecturas históricas no vinculadas.
- 258 correcciones verificadas en `P`: 52 llenados y 206 reemplazos.
- Casos `Oficina de Correspondencia…` corregidos a las denominaciones `O.C.C…` almacenadas en Atlas.
- Los equipos sin lectura histórica no recibieron valores en `R,S,V,W`.

