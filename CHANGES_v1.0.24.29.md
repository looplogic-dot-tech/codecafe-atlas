# CodeCafe Atlas v1.0.24.29

## Alta masiva de equipos desde contadores

- El guardado explícito de una lectura o lote comprueba cada número de serie
  contra la tabla canónica `atlas_equipment`.
- Las variaciones de espacios, guiones, puntos y mayúsculas se normalizan para
  no crear duplicados.
- Si aparecen series desconocidas, Atlas presenta una sola confirmación con la
  lista de equipos detectados.
- La dependencia seleccionada en **Datos comunes del reporte Excel** se utiliza
  para todo el lote. Si está en **Sin especificar**, Atlas permite elegir una
  dependencia activa una sola vez.
- **Registrar y guardar** crea todos los equipos nuevos como `Impresora`, estado
  `Activo`, con la serie y el modelo detectados. La marca solamente se completa
  cuando aparece explícitamente al principio del modelo.
- No se inventan número de inventario, dirección IP, hostname ni usuario.
- **Guardar solo lecturas** conserva el comportamiento previo sin crear equipos.
- **Cancelar** no guarda la operación ni marca los elementos del lote como
  procesados.
- Las lecturas históricas sin equipo cuya serie coincide se vinculan al nuevo
  registro.
- Directorio, Inventario y Órdenes de servicio se actualizan después del alta.

## Protección

- La sincronización automática del respaldo local al iniciar no abre diálogos
  ni registra equipos antiguos sin autorización.
- No hay cambios de esquema ni migraciones de base de datos.
- Se conserva la navegación `Enter` y `Flecha arriba/abajo` de v1.0.24.28.

