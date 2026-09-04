# CodeCafe Atlas v1.0.24.33

## Herramientas auxiliares

- Añade una entrada configurable para el Separador de PDFs por dependencia.
- Mantiene el separador como proceso independiente para aislarlo del núcleo estable de Atlas.
- Al ejecutarlo, Atlas proporciona automáticamente la ruta de `atlas.db`.
- En Linux, los lanzadores `.sh` se ejecutan con Bash para respetar sus instrucciones reales.

## Separador externo v0.1.5

- Usa `kdialog` en KDE Plasma para seleccionar PDFs y carpetas con la experiencia nativa asociada a Dolphin.
- Si `kdialog` no está disponible, conserva automáticamente el selector portátil de Tk.
- Admite recibir la ruta de la base desde Atlas sin convertir el arranque gráfico en modo CLI.
