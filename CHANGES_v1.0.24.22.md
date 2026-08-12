# CodeCafe Atlas v1.0.24.23

- Corrige el arranque con una instalación nueva/limpia: una DB inexistente o de 0 bytes crea directamente el esquema Atlas actual.
- La migración heredada solo se ejecuta cuando están presentes las tablas heredadas que esa migración realmente requiere (`buildings`, `locations`, `dependencies`, `equipment`).
- Una DB de estructura desconocida ya no se interpreta a ciegas como legacy ni se modifica: Atlas la rechaza con un mensaje claro para usar la previsualización/importación de Administrar datos.
- Se elimina la recuperación automática desde carpetas hermanas de otras builds/versiones. Una instalación nueva ya no puede apropiarse por accidente de una DB vieja/experimental.
- Se conserva la compatibilidad de actualización in-place: una DB Atlas reconocida colocada explícitamente dentro del `data/` de la misma instalación puede adoptarse si `atlas.db` todavía no contiene datos.
- No cambia el esquema SQLite canónico ni el flujo manual Cargar/migrar base de datos existente.
