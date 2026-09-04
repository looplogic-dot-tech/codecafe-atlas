# CodeCafe Atlas v1.0.24.32

## Separador PDF: lotes grandes

- Las imágenes PIL de alta resolución se cierran inmediatamente después de cada operación OCR.
- Los resultados se entregan a la interfaz en bloques de ocho páginas.
- La conexión bloqueante entre trabajador e interfaz impone control de flujo y evita una cola ilimitada de miniaturas.
- La tabla suspende el repintado durante cada bloque y actualiza métricas una sola vez.
- El cálculo de altura pasó de recorrer todas las filas después de cada inserción a una operación constante.
- Se conserva el procesamiento en hilo secundario y la cancelación después de la página actual.

No se modificaron las reglas de OCR, extracción, clasificación, corrección manual, nombres, jerarquía de exportación, historial ni base de datos.
