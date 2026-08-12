# CodeCafe Atlas v1.0.24.21

## Corrección aprobada

- **Órdenes de servicio → Buscar / abrir carpeta** abre la carpeta que contiene la plantilla activa.
- En Linux/KDE se intenta Dolphin explícitamente con `--new-window`; después se conservan `kioclient`, `gio`, `xdg-open` y Qt como fallbacks.
- Atlas ya no considera suficiente que un helper simplemente arranque: lo observa brevemente y, si termina con error, prueba el siguiente método.

## Regla de regresión

Esta revisión conserva el guard acumulativo de funcionalidades aprobado en v1.0.24.18–20. Ningún cambio funcional previo se elimina deliberadamente.
