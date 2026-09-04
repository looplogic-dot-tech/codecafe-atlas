# CodeCafe Atlas v1.0.24.44

## Datos auxiliares del insertador de contadores

- Detecta por encabezado la fecha de toma del contador, el piso y la dirección IP, sin depender de letras fijas.
- Completa únicamente campos vacíos de la hoja maestra; no altera otros campos ni fórmulas.
- La fecha procede de la lectura histórica más reciente de cada serie.
- El piso procede de la dependencia asociada al equipo en Atlas.
- La IP registrada en Atlas se copia a la hoja cuando el campo está vacío.
- Opcionalmente, una IP válida presente en la hoja se importa a Atlas cuando el equipo carece de IP.
- Una IP existente en Atlas nunca se reemplaza automáticamente. Si difiere de la hoja, se genera una discrepancia.
- Antes de importar IP a Atlas se crea una copia de respaldo de la base de datos.

## Alcance conservado

- Se mantienen la coincidencia exacta de series, las advertencias por series parecidas, las altas autorizadas, el estado `En Operación`, la ubicación canónica y el mapeo seleccionable de contadores.
- No se incorporaron ni modificaron campos distintos de los solicitados.
