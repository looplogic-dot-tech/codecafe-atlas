# CodeCafe Atlas v1.0.24.30

## Captura segura de hostname desde Registro de contadores

- Los informes de configuración HP reciben una segunda lectura OCR focalizada
  en el campo `Nombre de host`.
- El hostname detectado se presenta y puede corregirse antes de guardar, tanto
  en la revisión ampliada como en la tabla del lote.
- Atlas localiza el equipo por su número de serie normalizado y completa el
  hostname únicamente cuando el inventario lo tiene vacío.
- Un hostname existente nunca se reemplaza automáticamente.
- Si el hostname detectado ya pertenece a otro equipo, Atlas conserva ambos
  registros y muestra el conflicto al usuario.
- Cuando el lote registra un equipo nuevo, guarda también el hostname detectado
  si no existe una colisión.
- No cambia el esquema SQLite y conserva las bases existentes.

## Compatibilidad acumulativa

- Se conserva la alta masiva de equipos de v1.0.24.29.
- Se conserva `Enter` para aplicar y revisar el siguiente documento, así como
  la navegación con flechas de v1.0.24.28.
- No se modifican los históricos de contadores ni los módulos aprobados.
