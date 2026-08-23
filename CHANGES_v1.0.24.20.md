# CodeCafe Atlas v1.0.24.20

## Directorio — selección y protección de edificios

- El campo **Edificio** de la dependencia ahora es un desplegable editable con todos los edificios existentes.
- Sigue siendo posible escribir un edificio nuevo.
- Se añadió el botón **＋ Nuevo edificio** dentro del diálogo de dependencia para crear un edificio con su dirección completa sin salir del flujo.
- Al seleccionar un edificio existente se muestran inmediatamente los campos de dirección heredados.
- Un nombre de edificio equivalente a uno existente no puede crear un duplicado.
- Un nombre de edificio similar muestra advertencia y exige confirmación explícita antes de crear uno distinto.
- La protección equivalente también se aplica en la capa de base de datos para impedir duplicados si la escritura no proviene de la interfaz.
- No se modifica el esquema SQLite.
