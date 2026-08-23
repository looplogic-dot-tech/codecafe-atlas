# CodeCafe Atlas v1.0.24.19

## Correcciones

- Directorio e Inventario vuelven a contar el mismo conjunto canónico de equipos (`atlas_equipment`).
- Directorio deja de depender de vistas de compatibilidad que podían repetir dependencias/equipos por relaciones CTA históricas.
- Órdenes de servicio carga dependencias y equipos directamente desde las tablas canónicas, por lo que **Actualizar datos** refleja la misma base compartida que Directorio e Inventario.
- **Buscar / abrir carpeta** intenta primero Dolphin/KDE en Linux y conserva fallbacks multiplataforma.
- No se modifica el esquema SQLite ni se migran/destruyen datos existentes.
