# CodeCafe Atlas v1.0.24.51

- Corrige una regresión de despliegue detectada en v1.0.24.50: cada compilación nueva podía abrir una base vacía o distinta dentro de su propia carpeta `dist`.
- La base operativa ahora persiste en el directorio de datos del usuario y se comparte entre actualizaciones.
- En la primera ejecución se recupera de forma no destructiva la base Atlas más completa encontrada en instalaciones anteriores.
- Ninguna base anterior se elimina ni modifica durante la migración.
- Conserva las mejoras de v1.0.24.50: carpeta de cédulas recordada, acciones siempre visibles y confirmación fuerte antes de borrar historial.
