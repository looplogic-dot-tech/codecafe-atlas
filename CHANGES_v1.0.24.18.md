# CodeCafe Atlas v1.0.24.18 — Recuperación funcional acumulativa

Esta versión no usa una versión antigua como rollback. Parte de v1.0.24.17 y convierte la historia preservada de Atlas en un contrato acumulativo de regresión.

## Principio

Una función documentada se conserva salvo que una solicitud posterior la haya sustituido o eliminado expresamente. En conflictos históricos gana la intención posterior comprobada.

## Funciones acumulativas protegidas

- Directorio completo y colapsable, dirección heredada del edificio, usuario opcional del equipo y política anti-duplicados organizacionales.
- Inventario con persistencia de edición, revisión/fusión continua de series duplicadas, numeración, total, búsqueda y orden natural ascendente/descendente.
- Administración de datos con previsualización, filtros, reemplazo con rollback, reset a vacío, backup y exportación editable a Excel.
- Registro de contadores con OCR/historial y la última UX: Zona, Dependencia, Notas, Mes; serie editable en lote y revisión de PDF/imagen.
- Insertador de contadores con coincidencia exacta de serie, Torreón, filas/rango autorizado, escritura exclusiva AK–AR, protección de fórmulas y reporte de discrepancias. La columna H permanece intacta.
- Separador PDF con revisión, giro, navegación, clasificación, Año/Mes/Categoría, folios únicos por sesión, historial, CSV y eliminación continua.
- Visor PDF con indexación, visor, duplicados exactos SHA-256, papelera y eliminación permanente confirmada.
- Órdenes de servicio con equipo existente/nuevo, precarga, vista previa, ciudad/estado editables, actualización de datos, apertura de carpeta y configuración inicial/reconfigurable de plantilla XLSX.
- Administración de formatos en modo biblioteca, manteniendo compatibilidad con los formatos guardados y la precarga de órdenes.
- Homologación canónica de la base limpia con backup, transacción, traducción de relaciones, integridad/FK y sin opción Mantener ambos.
- Dashboard personalizable, backup automático al cerrar y updater protegido.

## Corrección encontrada durante esta recuperación

El motor del Insertador ya respetaba la decisión v1.0.14 de escribir exclusivamente en AK–AR, pero quedaba un mensaje visual heredado de v1.0.5 afirmando que también escribía la columna H. Se corrigió el mensaje para reflejar el comportamiento real: H permanece intacta.

## Protección nueva

`validate_full_functionality.py` verifica acumulativamente las funciones anteriores. `validate_before_build.py` ejecuta también este guard, de modo que una futura compilación falla si desaparece alguna de estas características comprobadas.

No se modifica el esquema SQLite en esta versión.
