# CodeCafe Atlas v1.0.24.27

## Órdenes de servicio

- Hora de reporte, diagnóstico y solución en formato de 24 horas con segundos (`HH:mm:ss`).
- Compatibilidad de lectura con registros anteriores `HH:mm` y `hh:mm:ss AM/PM`.
- Editor de plantillas rápidas para Falla reportada.
- Las plantillas históricas se copian una sola vez al archivo administrado por el usuario.
- Todas las plantillas pueden editarse o eliminarse; `Entrada manual` permanece como modo fijo.

## Visor PDF

- Botón `Renombrar PDF…` y acceso `F2`.
- Conserva automáticamente `.pdf`, valida el nombre y nunca sobrescribe otro archivo.
- El documento permanece abierto y el índice se actualiza después del cambio.

## Biblioteca técnica

- Nuevo módulo separado del Visor PDF.
- Recuerda una carpeta raíz elegida por el usuario e indexa sus subcarpetas.
- No mueve ni duplica los archivos originales.
- Búsqueda por nombre, tipo y ruta; visor interno para PDF y apertura externa para otros formatos.

## Herramientas auxiliares

- Permite registrar las rutas de Data Bridge y del comparador de hojas de cálculo.
- Las ejecuta como aplicaciones independientes para no acoplar motores ausentes al núcleo de Atlas.
- No se reconstruyó ninguna herramienta sin su fuente real.

## Compatibilidad

- Sin cambios en el esquema de la base de datos de Atlas.
- Se conservaron los flujos de Directorio, Inventario, Contadores, Separador, Homologación, Formatos y apertura de carpetas.
