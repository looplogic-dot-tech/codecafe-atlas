# CodeCafe Atlas v1.0.24.16

## Configuración inicial del generador de cédulas

Al abrir por primera vez el módulo de órdenes de servicio/cédulas, Atlas presenta un asistente de configuración de plantilla.

- Permite usar la plantilla incluida o elegir un XLSX propio.
- Permite elegir la hoja que Atlas completará.
- Detecta los placeholders soportados automáticamente.
- Permite mapear cualquier campo soportado a una o varias celdas Excel mediante referencias como `M8` o `A15,K20`.
- La plantilla elegida se copia al área local administrada `data/service_templates/active_service_template.xlsx` para que el uso posterior no dependa de la ubicación original.
- La configuración puede reabrirse con **Configurar plantilla**.
- **Restaurar plantilla incluida** vuelve al perfil incluido y elimina el mapeo directo personalizado.

No se modifica el esquema de la base de datos ni los flujos de inventario, directorio, contadores, homologación o PDF.
