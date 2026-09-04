# CodeCafe Atlas v1.0.24.37

## Altas controladas de series faltantes

- El resumen diferencia lecturas históricas y series únicas; varias lecturas de un equipo ya no aparentan registros perdidos.
- El insertador puede agregar filas al final del bloque de equipos cuando una serie no existe en la hoja maestra.
- Las altas se muestran en la vista previa con su fila prevista antes de generar la copia.
- Se escriben solamente la serie, la localidad Torreón y las columnas de contador elegidas.
- La columna de estado se detecta por su encabezado en vez de asumir una letra fija; en `Agosto` se detecta correctamente `J`.
- Si cualquier contador efectivo es mayor que cero, `Almacenada` o vacío cambia a `En Operación`.
- Si todos los contadores son cero, el estado se conserva.
- Se conservan el estilo de la fila disponible, las fórmulas y el formato XLSX u ODS.
- Una distancia de edición o transposición de un carácter genera una advertencia de posible serie mal escrita o duplicada.
- La coincidencia aproximada nunca reemplaza a la coincidencia exacta.
- Por defecto, la serie dudosa queda bloqueada. El usuario puede autorizarla explícitamente después de revisar la candidata.
- Toda alta autorizada pese a una advertencia queda documentada en el CSV de discrepancias.

## Validación específica

- Caso `200 lecturas → 195 series únicas` verificado.
- Alta de una serie nueva verificada en la fila 391 de la pestaña `Agosto` con destinos `R,S,V,W`.
- Serie con un carácter diferente bloqueada y vinculada visualmente con la candidata existente.
- Autorización explícita de la serie advertida verificada y documentada.
- Escritura y reapertura verificadas en ODS y XLSX.
- Transición `J: Almacenada → En Operación` verificada con contador positivo; contador cero preserva `Almacenada`.
