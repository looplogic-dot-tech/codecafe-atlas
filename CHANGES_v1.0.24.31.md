# CodeCafe Atlas v1.0.24.31

## Acuerdo bilingüe de licencia de uso

- Incorpora texto completo en español e inglés, versión `2026-08-29.1`.
- Solicita aceptación antes de construir la ventana principal y antes de abrir
  la base de datos.
- Registra una aceptación independiente por usuario del sistema operativo.
- Vincula la aceptación al SHA-256 del texto exacto; modificarlo invalida las
  aceptaciones anteriores y obliga a revisarlo nuevamente.
- Conserva nombre, organización, fecha UTC, usuario, equipo, plataforma e
  identidad de la versión de Atlas.
- Permite consultar el acuerdo desde `Ayuda → Licencia de uso / Software License`.

## Separación de propiedad

- El Licenciatario conserva la propiedad y el control de sus datos operativos.
- CodeCafe conserva la propiedad de Atlas y una autorización de uso no equivale
  a venta ni cesión.
- Al terminar una licencia debe cesar el uso operativo, pero no se borran,
  cifran, apropian ni alteran los datos del Licenciatario.
- Los costos de una implementación web organizacional o nacional se definen en
  la orden de licencia y no recaen automáticamente en el Licenciante.

## Compatibilidad

- No existe migración ni cambio del esquema SQLite.
- La aceptación se guarda en `data/license_acceptances.json` mediante escritura
  atómica.
- Se conservan todas las validaciones acumulativas hasta v1.0.24.30.
