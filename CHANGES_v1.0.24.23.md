# CodeCafe Atlas v1.0.24.23 — External folder opener fix

- Corrige apertura de carpetas desde el ejecutable PyInstaller en Linux/KDE.
- Los procesos externos ya no heredan `LD_LIBRARY_PATH` modificado por PyInstaller; se restaura `LD_LIBRARY_PATH_ORIG` o se elimina la ruta empaquetada antes de lanzar Dolphin/gio/xdg-open.
- Unifica el lanzador de carpetas en Órdenes de servicio, Registro de contadores y Visor PDF.
- Si ningún administrador de archivos abre, Atlas muestra el diagnóstico real en lugar de fallar silenciosamente.
- No cambia el esquema SQLite ni la lógica funcional de los módulos.
