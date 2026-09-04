# CodeCafe Atlas v1.0.24.42

## Insertador de contadores

- Reserva la columna detectada como `Ubicación de Equipo` cuando está activa la sincronización de dependencia.
- Normaliza automáticamente un mapeo manual `P,R,S,V,W` a `R,S,V,W`, evitando utilizar `P` simultáneamente como ubicación y contador.
- La detección automática excluye la columna de ubicación de los candidatos de contador.
- Conserva la protección original de la pestaña y las fórmulas de la hoja maestra.

## Administración de datos

- Homologación dejó de ocupar una entrada independiente en la navegación lateral.
- Ahora se encuentra dentro de `Administrar datos`, en una pestaña propia junto a las operaciones de base de datos.
- Se conserva la ruta interna `sync_compare` para accesos existentes, redirigiéndola a la pestaña de Homologación.

