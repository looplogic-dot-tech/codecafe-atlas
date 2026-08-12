# CodeCafe Atlas v1.0.24.23

## Recuperación funcional acumulativa

Esta fuente protege como contrato acumulativo las funciones verificadas de las versiones preservadas. Antes de compilar, `validate_before_build.py` ejecuta también `validate_full_functionality.py` para detectar regresiones de Directorio, Inventario, Administración de datos, contadores, Insertador, Separador, Visor PDF, Órdenes, Formatos, Homologación, backups y updater.


## v1.0.24.16 — Configuración inicial del generador de cédulas

- La primera apertura del generador solicita configurar la plantilla de Cédula de Servicio.
- Puede utilizarse la plantilla incluida o copiar una plantilla XLSX propia al espacio administrado de Atlas.
- Los placeholders `{{CAMPO}}` se detectan automáticamente.
- Como alternativa o complemento, cada campo puede mapearse directamente a una o varias celdas Excel.
- La hoja de destino es seleccionable, por lo que una plantilla propia no necesita usar el nombre de hoja predeterminado.
- La configuración queda en `data/service_template_config.json` y la plantilla administrada en `data/service_templates/`.
- No se modifica el esquema SQLite ni la compatibilidad con bases Atlas existentes.

## v1.0.24.13 — Exportación editable a Excel

En **Administrar datos** y en el menú **Archivo** se puede exportar la base maestra a un `.xlsx` editable. El libro contiene una sola hoja `Inventario Atlas`, con una fila por equipo y el contexto de edificio, dirección detallada, piso, dependencia, CTA, oficina y usuario asignado. Los encabezados usan etiquetas de negocio compatibles con Atlas Data Bridge / Asistente de migración. No se incluyen IDs, UUID, claves foráneas ni campos técnicos. La exportación no modifica SQLite.


## Experimento de interfaz visual para el directorio

La pestaña **Directorio** adopta una vista inspirada en el HTML de referencia:

- Encabezado visual.
- Buscador y filtros por edificio y piso.
- Dependencias agrupadas por edificio.
- Dirección visible en cada edificio.
- Insignias de piso.
- CTA y tipo visibles sin abrir el registro.
- Clic en la dependencia para abrir una ventana editable.
- Botones directos Editar y Eliminar.
- Conserva la misma base SQLite; inventario y órdenes siguen vinculados.


Aplicación portátil para:

- Separar PDF por número de serie.
- Registrar contadores.
- Mantener el directorio de dependencias.
- Administrar el inventario de equipos.
- Generar órdenes de servicio y cédulas desde la plantilla oficial.

## Cambios principales de v0.7

### Captura de equipos nuevos desde una orden de servicio

En **Órdenes de servicio** ahora se puede trabajar de dos formas:

1. Seleccionar un equipo ya registrado en la dependencia.
2. Activar **Equipo nuevo: capturar manualmente y agregarlo al inventario**.

Al activar la captura manual se habilitan los campos:

- Tipo de equipo.
- Marca.
- Modelo.
- Número de serie.
- Número de inventario.
- IP.
- Hostname.
- Estado inicial.

Al guardar la orden o generar la cédula, el equipo se agrega automáticamente al inventario de la dependencia seleccionada.

Para identificar un equipo nuevo se requiere el tipo y al menos uno de estos datos:

- Número de serie.
- Número de inventario.
- Hostname.

### Prevención de duplicados

Antes de insertar un equipo, la aplicación compara de forma normalizada:

- Número de serie.
- Número de inventario.
- Hostname.

Las mayúsculas, espacios y guiones no crean registros diferentes. Por ejemplo, `ABC-123` y `abc 123` se consideran el mismo identificador.

- Si la coincidencia pertenece a la misma dependencia, se utiliza el registro existente y no se crea un duplicado.
- Si pertenece a otra dependencia, la aplicación detiene el registro e indica que debe reasignarse desde **Inventario**.
- La misma verificación también se aplica al guardar directamente desde la pantalla **Inventario**.

### Dependencia y CTA

La dependencia continúa siendo obligatoria. Al seleccionarla se cargan automáticamente:

- Dirección.
- Ciudad y estado.
- Edificio, piso y oficina.
- CTA registrado.
- Teléfono y correo.

El CTA se usa inicialmente como responsable del equipo y como servidor público que valida; ambos campos siguen siendo editables.

### Ayuda y contacto

El menú **Ayuda** incluye:

- Acerca de.
- Contacto.

Responsable: **Jaime Sánchez Sáenz**  
Contacto: **contacto@codecafe.io**

## Migrar desde CodeCafe Atlas v0.24.8

CodeCafe Atlas v1.0.0 conserva `data/atlas.db` para no perder información. La transición puede hacerse mediante el paquete puente generado con `--legacy-transition`, que es aceptado por el actualizador de v0.24.8.

No elimines la instalación anterior ni su respaldo hasta confirmar que aparecen las dependencias, equipos, contadores y órdenes de servicio.

## Ejecutar en Kubuntu/Linux

```bash
chmod +x run_linux.sh
./run_linux.sh
```

## Ejecutar en Windows

Ejecuta:

```text
run_windows.bat
```

## Datos

La fuente pública no incluye ninguna base operacional. En el primer arranque Atlas crea `data/atlas.db` con el esquema vigente.

Desde **Administrar datos** puede previsualizarse o reemplazarse la base activa usando las mismas bases SQLite compatibles aceptadas por v1.0.24.16. Si se coloca una base Atlas compatible con cualquier nombre `.db`, `.sqlite` o `.sqlite3` dentro de `data/`, Atlas puede recuperarla automáticamente cuando la base activa está vacía.


## Corrección v0.9

- Se corrigió el encabezado azul del módulo **Directorio**.
- El título y el subtítulo ahora tienen fondo transparente y contraste blanco.
- Se evita que el estilo general de las ventanas convierta los textos del encabezado en barras blancas.


## Corrección v0.10 — separador detenido en 0 %

El OCR basado en el módulo HTML puede quedar bloqueado dentro de Qt WebEngine.
Esta versión utiliza dos modos:

- **Vista integrada:** analiza la capa de texto del PDF y permite revisión manual.
  El OCR se desactiva automáticamente para impedir que el proceso se congele.
- **Abrir en navegador para OCR:** abre el mismo módulo en Firefox, Edge, Chrome
  u otro navegador predeterminado, donde puede ejecutarse el OCR completo.

La aplicación recupera automáticamente el separador HTML importado en la
versión anterior cuando ambas carpetas están una junto a la otra.


## Corrección v0.11 — servidor local para PDF.js y OCR

La versión anterior seguía cargando el separador como un archivo `file://`.
Eso puede impedir que PDF.js o Tesseract creen correctamente sus procesos
auxiliares y el análisis puede quedarse en la primera página.

Ahora el módulo se sirve exclusivamente dentro de la computadora mediante una
dirección similar a:

```text
http://127.0.0.1:43821/index.html
```

`127.0.0.1` es la propia computadora. Los PDF seleccionados no se envían a
CodeCafe Atlas, LoopLogic ni a otro servidor.

### Cambios

- Se eliminó la desactivación temporal del OCR introducida en v0.10.
- PDF.js y Tesseract se ejecutan desde un origen HTTP local.
- El botón **Abrir en navegador** usa la misma dirección local.
- La primera página muestra al menos 1 % al comenzar.
- Los errores de bibliotecas o JavaScript se muestran dentro del módulo.
- El separador importado se recupera automáticamente desde la versión anterior.


## Versión v0.12 — primer módulo completamente nativo

El módulo **Separador PDF** ya no usa HTML, JavaScript, PDF.js ni Qt WebEngine.
La interfaz fue reconstruida en PySide6 manteniendo la apariencia y el flujo
aprobados en la versión HTML.

### Funciones incluidas

- Selección de uno o varios PDF.
- Exploración de una carpeta completa y sus subcarpetas.
- Arrastrar y soltar archivos.
- Extracción directa de texto con PyMuPDF.
- OCR únicamente cuando la página no contiene texto reconocible.
- Progreso real y cancelación.
- Indicadores de páginas, series detectadas, faltantes y repetidas.
- Tabla de revisión con miniaturas.
- Edición manual de números de serie.
- Eliminación mediante botón de papelera.
- Ventana de revisión ampliada.
- Tecla Enter para guardar y avanzar a la siguiente página sin serie.
- Exportación ZIP con selección de ubicación.
- Nombres provisionales para páginas sin serie.
- Procesamiento completamente local.

### OCR del sistema

PyTesseract usa el programa Tesseract instalado en el sistema.

En Kubuntu/Ubuntu:

```bash
sudo apt install tesseract-ocr tesseract-ocr-spa
```

En Windows será necesario incluir Tesseract dentro del paquete portátil final
o instalarlo durante la fase de pruebas.

El módulo **Registro de contadores** permanece sin cambios en esta versión y
será el siguiente en migrarse a Python nativo.


## Corrección v0.13 — conservar el trabajo al cambiar de pestaña

En v0.12, cada vez que el usuario regresaba a **Registro de contadores**,
la navegación volvía a cargar `index.html`. Eso eliminaba de la memoria del
módulo:

- Documentos seleccionados.
- Resultados de OCR.
- Campos corregidos.
- Datos comunes del reporte.
- Estado del lote procesado.

La navegación ahora conserva cada pantalla exactamente como quedó. El Registro
de contadores solamente se reinicia cuando el usuario pulsa explícitamente
**Actualizar / recargar**, reemplaza el módulo HTML o cierra la aplicación.

El separador PDF nativo también conserva sus resultados, series corregidas y
estado de exportación al visitar otros módulos.


## Corrección v0.14 — texto unido al número de serie

El OCR podía unir la palabra siguiente al número de serie:

```text
VNB0B01173CONFIGURACI
VNB0B02009NPREDAUTOGES
```

El extractor reconoce primero los formatos HP presentes en los reportes y
recorta exactamente:

```text
VNB0B01173
VNB0B02009
```

También se evita que el patrón de «Número de serie» absorba palabras separadas.
La captura manual sigue disponible para números con otros formatos.


## Versión v0.15 — segundo formato de registro de contadores

Registro de contadores reconoce ahora dos diseños:

### Informe de configuración HP

Extrae serie, total, equivalentes, dúplex, atascos, errores de alimentación y
Economode.

### Formato compacto Counter

Reconoce hojas con campos como:

```text
Counter
Serial No.: 3355PC50155
Data of Today: Jul. 15, 2026 01:33 PM
Total 5457
```

Para este formato se guardan:

- Número de serie: `3355PC50155`
- Total de impresiones: `5457`

Los campos Oficio, Carta, Dúplex, Atascos, Mal alimentación y Economode se
dejan vacíos porque la hoja no proporciona esos datos. El formato compacto se
considera completo cuando se detectan tanto la serie como el total.


## Versión v0.16 — revisión legible y entradas repetidas

### Imagen de revisión en alta resolución

La ventana **Examinar página y corregir número de serie** ya no amplía la
miniatura de la tabla. Abre directamente la página original del PDF y la
renderiza a alta resolución.

- La ventana abre ocupando casi toda la pantalla.
- La imagen se ajusta automáticamente al ancho disponible.
- Se añadió el botón **Ajustar al ancho**.
- Los controles `+` y `−` amplían una fuente de alta resolución, evitando el
  desenfoque de la versión anterior.
- Cada página se carga desde su PDF original únicamente al revisarla, por lo
  que no se almacenan decenas de imágenes grandes en memoria.

### Verificación de entradas repetidas

Se añadió el botón **Examinar entradas repetidas** junto a la revisión de
páginas sin serie.

- El botón muestra cuántas entradas pertenecen a series repetidas.
- Abre la primera repetida y permite avanzar con Enter.
- El campo de serie aparece resaltado en amarillo dentro de la tabla.
- Al corregir una serie, los indicadores y resaltados se actualizan.
- El indicador superior conserva el conteo de repeticiones adicionales.


## Versión v0.17 — contadores en la base común

Los resultados guardados desde **Registro de contadores** ahora se almacenan
en `data/atlas.db`, dentro de la tabla `counter_records`.

Se conservan fecha, serie, modelo, archivo, total, oficio, carta, dúplex,
atascos, mal alimentación, Economode y formato detectado. Cuando la serie
coincide con un equipo del inventario, el registro queda relacionado con ese
equipo.

En la primera apertura, el historial local visible se migra automáticamente a
SQLite. El historial mostrado después procede de la base común y se incluye en
respaldos y migraciones.

## Una sola barra vertical en Separador PDF

La tabla de revisión aumenta su altura según el número de páginas. Se desactivó
su barra vertical interna y toda la navegación utiliza la barra exterior del
módulo.


## Versión v0.18 — ventana completa para revisar contadores

El botón **Revisar** del lote abre ahora una ventana de revisión que ocupa casi
toda el área disponible.

### Documento

- Carga el PDF original hasta aproximadamente 4300 píxeles por lado.
- Las imágenes utilizan su resolución original.
- Ajuste automático al ancho.
- Zoom entre 12 % y 250 %.
- Rotación izquierda y derecha.
- Navegación al documento anterior o siguiente.
- El documento permanece nítido al ampliar porque no se reutiliza la miniatura.

### Campos editables

La ventana permite corregir:

- Número de serie.
- Modelo.
- Fecha del registro.
- Total de impresiones.
- Impresiones tamaño oficio.
- Impresiones tamaño carta calculadas.
- Hojas dúplex.
- Atascos.
- Páginas mal alimentadas.
- Economode.

**Aplicar correcciones** actualiza el lote sin crear todavía un registro en la
base. **Aplicar y revisar siguiente** conserva los cambios y avanza al siguiente
documento. Los resultados pueden guardarse posteriormente mediante los botones
normales del lote.


## Versión v0.19 — limpieza del modelo y nombre de contacto

### Modelo de impresora

El OCR podía producir resultados como:

```text
HP LaserJet Pro M501dn Descr
HP LaserJet Pro M501dn Descr. disp.
```

El extractor corta ahora el modelo antes de etiquetas posteriores como:

- Descr. / Descripción / Descrip. disp.
- Número formateador.
- Número de serie.
- Configuración.
- Idioma.
- Índice de cartuchos.
- ID de servicio.
- Código de firmware.
- Zona y ubicación del dispositivo.

El resultado esperado es:

```text
HP LaserJet Pro M501dn
```

### Ayuda y contacto

El nombre se corrigió en **Acerca de** y **Contacto**:

```text
Jaime Sánchez Sáenz
contacto@codecafe.io
```


## Versión v0.20 — OCR nativo para Registro de contadores

El Registro de contadores ya no carga normalmente Tesseract.js, WebAssembly ni
el archivo de idioma español al iniciar un lote.

Cuando CodeCafe Atlas detecta `tesseract-ocr` instalado:

1. El HTML prepara únicamente la zona de imagen que debe reconocerse.
2. La envía internamente mediante QWebChannel.
3. Python ejecuta Tesseract local en un hilo independiente.
4. El texto vuelve al módulo para extraer serie, modelo y contadores.

La interfaz permanece activa durante el reconocimiento y muestra
**OCR nativo listo · spa+eng** cuando los idiomas están disponibles.

### Ventajas

- No descarga de nuevo el motor OCR.
- No muestra «Cargando idioma español» en uso normal.
- Funciona sin Internet para el reconocimiento.
- Utiliza `tesseract-ocr-spa` ya instalado.
- Mantiene Tesseract.js únicamente como respaldo cuando falta el motor nativo.

PDF.js y ExcelJS siguen siendo recursos web del módulo actual; pueden requerir
Internet en la primera carga. La futura migración completamente nativa eliminará
también esa dependencia.


## Versión v0.21 — selección automática de carpeta para cédulas

El botón **Guardar y generar cédula** ya no muestra directamente el error:

```text
Selecciona la carpeta donde se guardará la cédula.
```

Cuando el campo **Guardar en** está vacío:

1. Se validan los demás datos.
2. Se abre automáticamente el selector de carpetas.
3. Después de elegir una ubicación se genera la cédula.
4. Si el selector se cancela, no aparece un error ni se crea un registro
   incompleto.

La aplicación recuerda la última ubicación seleccionada en:

```text
data/service_order_settings.json
```

Esa carpeta aparece automáticamente en las siguientes órdenes y se conserva al
actualizar la aplicación junto con la carpeta `data`.

También se corrigió una protección interna del recuperador de bases para que
siempre devuelva los cuatro conteos esperados: dependencias, equipos, órdenes y
contadores.


## Versión v0.22 — ventana de dependencias adaptable en Windows

La ventana **Nueva entrada / Información de la dependencia** fue ajustada para
pantallas Windows con escalado de 125 %, 150 % o resoluciones reducidas.

- La ventana puede redimensionarse y maximizarse.
- El formulario tiene barra de desplazamiento vertical.
- Los botones **Cancelar** y **Guardar entrada** permanecen fijos abajo.
- La barra horizontal está desactivada.
- Los campos se adaptan al ancho disponible.
- La altura inicial se calcula según el área útil de la pantalla.
- Al abrir la ventana, el formulario comienza desde la parte superior.

El funcionamiento en Linux permanece igual.


## Actualizador integrado — estado en v1.0.0

El menú **Ayuda → Actualizar CodeCafe Atlas…** acepta paquetes oficiales con nombres como:

```text
CodeCafe-Atlas-update-1.0.9-windows-x86_64.zip
```

Los ejecutables oficiales son:

```text
CodeCafe-Atlas.exe
CodeCafe-Atlas-Updater.exe
```

Para generar un paquete normal:

```bat
.venv\Scripts\python.exe make_update_package.py ^
  --dist dist\CodeCafe-Atlas ^
  --version 1.0.9 ^
  --platform windows ^
  --architecture x86_64 ^
  --notes NOTAS_ACTUALIZACION.txt
```

Para crear exclusivamente el paquete puente que puede instalar v0.24.8:

```bat
.venv\Scripts\python.exe make_update_package.py ^
  --dist dist\CodeCafe-Atlas ^
  --version 1.0.0 ^
  --platform windows ^
  --architecture x86_64 ^
  --legacy-transition
```

El actualizador conserva las carpetas `data` y `backups`, valida los hashes SHA-256 y crea un respaldo de la instalación anterior. Los alias técnicos `CodeCafe-Atlas` y `CodeCafe-Atlas-Updater` existen temporalmente solo para completar esta primera migración.


## v0.23.1 — actualización estable

Esta versión parte exclusivamente de v0.23. Corrige el actualizador en Linux y Windows sin incorporar cambios funcionales posteriores.

- Conserva permisos ejecutables mediante el manifiesto schema 2.
- Rechaza carpetas CodeCafe-Atlas anidadas.
- Verifica que el ejecutable principal sea archivo.
- Aplica chmod antes de reiniciar en Linux.
- Restaura la instalación anterior si falla la sustitución.
- build_linux.sh y build_windows.bat validan la estructura final.
- El ejecutable intermedio del updater se elimina de dist; solo queda dentro de la carpeta final.


## v0.23.3

Reconstruida desde v0.23.1 estable. Añade las plantillas de Falla reportada
con la indentación correcta y una validación AST obligatoria antes del build.
El build de Linux también ejecuta una prueba de arranque y falla si detecta
Traceback, AttributeError o error de PyInstaller.


## v0.23.5 — Directorio completo

- Dirección completa visible bajo cada edificio.
- Encabezado del edificio clicable y botón **Editar edificio**.
- Edición segura de nombre y dirección sin romper dependencias, equipos, contadores ni órdenes.
- Botón **+ Añadir edificio** junto a **+ Nueva entrada**.
- Equipos y último contador visibles por dependencia en secciones colapsables, cerradas por defecto.
- Tabla canónica de edificios e índices de consulta; la compatibilidad con los demás módulos se conserva.

## v0.23.9 — Respaldo adicional OCR.Space

Cambio único de esta versión:

- Se conserva el flujo existente de OCR nativo con Tesseract.
- Si el OCR nativo no está disponible o falla durante una lectura, se intenta Tesseract.js, como en la versión anterior.
- Si Tesseract.js tampoco puede cargarse o procesar el documento, se intenta OCR.Space como último respaldo.
- Antes de usar OCR.Space se informa que requiere conexión a Internet y que la imagen se enviará temporalmente al servicio externo.
- Si no existe conexión o los tres métodos fallan, se muestra un error con el detalle de cada intento.

No se modificaron otros módulos ni comportamientos de la aplicación.
## v0.23.12 — Reporte de contadores simplificado

Cambio único de esta versión:

- La exportación Excel y CSV deja de usar las columnas de la antigua plantilla de inventario.
- Se conserva el estilo visual profesional con encabezado azul, bordes, filtros y anchos legibles.
- El reporte contiene únicamente: ID, zona, modelo, número de serie, fecha, total, oficio, carta, dúplex, atascos, páginas mal alimentadas y formato del informe.
- Impresiones tamaño oficio permanece vacío.
- Los informes Counter exportan solo serie, fecha y total; los campos que no existen en ese formato permanecen vacíos.
- No se añadieron fórmulas ni se modificó el OCR.



## v0.23.13 — Biblioteca PDF inicial

- Añade el módulo Biblioteca PDF.
- Selecciona e indexa recursivamente una carpeta local sin mover archivos.
- Busca por nombre y ruta.
- Muestra nombre, ubicación, tamaño y fecha de modificación.
- Incluye visor PDF local con páginas, zoom, ajuste al ancho y rotación.
- Permite abrir el PDF o su carpeta original.


## v0.23.14 — Historial de contadores por fecha

- “Historial común” se renombra a “Historial de contadores”.
- Los registros se agrupan por fecha en secciones colapsables.
- La fecha más reciente se muestra abierta inicialmente y las anteriores cerradas.
- No se modifica OCR, exportación, base de datos ni otros módulos.


## v0.23.17 — Cédulas de servicio en Separador PDF

- Añade un selector de tipo de documento: equipos por número de serie o cédulas por folio/reporte.
- En cédulas prioriza el número de reporte del prestador de servicio (REQ...) y admite folios alternativos.
- Usa texto directo en documentos generados digitalmente.
- Para escaneos aplica OCR local sobre el encabezado con varios modos de segmentación.
- La escritura manuscrita se procesa como mejor esfuerzo y siempre puede revisarse/corregirse antes de exportar.
- No modifica Registro de contadores ni otros módulos.

## v0.23.17 — Clasificación configurable de cédulas por sesión

- Antes de analizar cédulas de servicio, permite definir categorías y palabras clave temporales.
- Configuración inicial: `Tóner` y `Resto de fallas`.
- Permite añadir o eliminar categorías para cada sesión sin alterar una configuración permanente.
- Clasifica el campo de falla reportada mediante texto digital u OCR local de la zona correspondiente.
- La categoría puede corregirse manualmente en la tabla o en la ventana de revisión.
- El ZIP exporta cada cédula dentro de la subcarpeta de su categoría.


## v0.23.17 — Dependencia en reportes de contadores

- Añade un menú desplegable de Dependencia en los datos comunes del reporte.
- Las opciones se leen del Directorio de dependencias existente.
- La dependencia se incluye como columna en Excel y CSV y en el nombre del archivo.
- No consulta, compara ni modifica equipos del Inventario.


## v0.23.19 — Plantilla de cédula de servicio actualizada

- La hoja «Cédula de Servicio» usa como referencia el formato ajustado manualmente y validado con el folio CodeCafe Atlas-REQ101186.
- Se conserva la distribución revisada de encabezado, datos del responsable, falla reportada, diagnóstico, solución, observaciones y firmas.
- Las plantillas de Mantenimiento Preventivo y Dictaminación permanecen sin cambios.
- El generador continúa reemplazando los valores variables en las mismas posiciones de la nueva plantilla.


## v0.23.19 — Motor de Plantillas (fase 1)

- La Cédula de Servicio se genera sustituyendo placeholders dentro de una plantilla Excel editable.
- La plantilla activa puede reemplazarse sin recompilar la aplicación.
- Incluye validación de placeholders obligatorios y desconocidos.
- Conserva respaldo de la plantilla anterior y permite restaurar la plantilla incluida.
- Mantenimiento Preventivo y Dictaminación mantienen su funcionamiento anterior.


## v0.23.24 — Dashboard personalizable

- Selección de wallpaper local en PNG, JPG, JPEG o WebP.
- Modos Rellenar, Ajustar, Centrar y Mosaico.
- Control de opacidad.
- Restauración del fondo predeterminado.
- La imagen y la configuración se guardan en `data/dashboard/`.


## v0.23.24 — Identidad para homologación de bases

- UUID permanente por instalación.
- UUID permanente por edificio, ubicación, dependencia, equipo, cédula y lectura de contador.
- Metadatos de procedencia, revisión y eliminación lógica.
- Migración automática con respaldo previo.
- Esta fase no fusiona bases ni presenta todavía una interfaz de homologación.


## v0.23.24 — Confirmación única al generar cédula

Se eliminan las confirmaciones al cambiar la plantilla de falla reportada. La confirmación se solicita únicamente al iniciar la generación de la cédula.


## v0.23.24 — Impresión automática de cédulas

- Configura la cédula generada en tamaño Carta y orientación vertical.
- Define el área de impresión A1:M64.
- Ajusta automáticamente a una página de ancho por una de alto.
- Centra horizontalmente y aplica márgenes reducidos.
- No modifica otros módulos ni otros tipos de documento.


## v0.23.24 — Vista previa de cédula antes de generar

- Añade el botón **Vista previa de cédula** junto a las acciones de guardado.
- Presenta en una ventana desplazable los datos actuales del formulario.
- No guarda registros ni genera archivos al abrir la vista previa.
- El archivo definitivo continúa usando la plantilla Excel configurada.


## v0.23.26 — Rótulos verticales en cédula

- Conserva verticales los rótulos laterales del bloque de firmas.
- Corrige las celdas combinadas A53:A64 y H53:H64.
- El ajuste se aplica tanto a la plantilla incluida como al archivo generado.


## v0.23.26 — Analizador de homologación

Añade comparación de una base externa contra la base local, sin modificar ni fusionar registros. Clasifica nuevos, coincidentes, conflictos, posibles duplicados y registros solo locales. Permite exportar el análisis a CSV.

## v0.23.27 — Insertador inteligente de contadores

Se integra como módulo nativo el Insertador inteligente de contadores local v0.4.

- Selecciona hoja maestra XLSX u ODS y uno o varios reportes CSV/XLSX/ODS compatibles.
- Relaciona equipos por número de serie, con corrección OCR única y segura.
- Trabaja exclusivamente en la hoja de consumo, filas 821–1404.
- Solo procesa equipos cuya localidad sea Torreón.
- Solo escribe en AK–AR y nunca modifica fórmulas.
- No agrega columnas, hojas ni campos.
- Presenta análisis y vista previa antes de generar.
- Guarda una copia nueva y verifica nuevamente el archivo producido.

## v0.23.28 — Insertador de contadores v0.4.2

Se actualizó exclusivamente el motor del módulo **Insertador de contadores** a la versión local v0.4.2 proporcionada por el usuario.

Cambios principales del motor:

- detección automática de la columna real de número de serie en la hoja maestra (E o F, según la disposición histórica);
- detección automática de la columna LOCALIDAD y de la fila de encabezados;
- validación estructural dinámica antes del análisis y nuevamente antes de escribir;
- conservación visible de los ceros insertados en XLSX sin alterar bordes, rellenos, fuentes ni alineación;
- complemento con cero también cuando los contadores compatibles ya coinciden con los valores existentes, siempre que no haya conflictos;
- se mantienen las restricciones: Torreón, filas 821–1404, columnas AK–AR, sin agregar estructuras ni modificar fórmulas.


## v0.24.1 — Corrección del menú Ayuda

- La versión mostrada en la ventana principal y en **Ayuda → Acerca de** ahora se obtiene de `codecafe_atlas.__version__`, evitando que vuelva a quedar desactualizada.
- Se unificó el contacto oficial de la aplicación como **contacto@codecafe.io**.
- No se modificó el motor de homologación ni ningún otro módulo funcional.


## v0.24.3 — Botón de copia del Insertador

- El botón **Generar copia actualizada** queda disponible después de todo análisis correcto, incluso cuando no hay celdas nuevas.
- En ausencia de cambios, genera una copia verificada y muestra claramente que no se insertaron contadores.
- Se impide seleccionar la hoja maestra original como archivo de salida.
- No se modificaron los criterios de análisis, el rango AK–AR, las filas 821–1404 ni otros módulos.


## v0.24.3 — Indicador de progreso del insertador

- El análisis y la generación se ejecutan en un hilo de trabajo para mantener la interfaz receptiva.
- Se muestra una barra de actividad mientras el motor procesa archivos.
- El estado describe la etapa activa: análisis o generación/verificación.
- Los selectores y opciones quedan bloqueados temporalmente para impedir cambios durante el proceso.
- No se modificaron las reglas de escritura ni otros módulos.


## v0.24.4 — Varias fuentes contra una hoja maestra

- El Insertador inteligente permite añadir varios reportes CSV, XLSX u ODS.
- Todas las fuentes se analizan conjuntamente contra una sola hoja maestra.
- Equipos distintos se consolidan en una misma vista previa.
- Campos complementarios del mismo equipo se combinan de forma segura.
- Valores idénticos repetidos se consolidan sin duplicar escrituras.
- Valores diferentes para la misma celda se marcan como conflicto entre fuentes y no se escriben automáticamente.
- La tabla identifica el archivo o archivos que aportaron cada registro.
- Se mantienen las restricciones AK–AR, filas 821–1404 y protección absoluta de fórmulas.


## v0.24.5 — Estado “En Operación” derivado de contadores

- El Insertador inteligente incorpora la columna **H** como destino derivado y controlado.
- H se actualiza exactamente a **“En Operación”** únicamente para números de serie de **Torreón**, dentro de las filas **821–1404**, cuyo valor final tenga al menos un contador estrictamente mayor a **0** en **AK–AR**.
- Para determinar la condición se consideran los valores que permanecerán en la copia: valores nuevos, valores iguales y valores existentes conservados.
- Cuando todos los contadores son 0, están vacíos o no producen un valor final mayor a 0, la columna H permanece intacta.
- La regla no elimina ni sustituye estados de filas no elegibles.
- Si H contiene una fórmula, permanece protegida y no se modifica.
- La vista previa identifica H entre las celdas que serán escritas y muestra el estado existente, la condición evaluada y la acción resultante.
- La verificación posterior reabre la copia y confirma tanto los valores numéricos de AK–AR como el texto escrito en H.
- Se conservan las demás restricciones: solo Torreón, filas 821–1404, sin agregar columnas u hojas y sin modificar fórmulas.


## v0.24.6 — Barras de desplazamiento en Biblioteca PDF

- El visor integrado conserva el tamaño real de la página PDF renderizada.
- La barra vertical aparece automáticamente cuando la página excede la altura visible.
- La barra horizontal aparece cuando el zoom o la rotación exceden el ancho disponible.
- Las barras se recalculan al cambiar de página, aplicar zoom, girar o ajustar al ancho.
- No se modificaron el índice, la búsqueda, la apertura externa ni otros módulos.


## v0.24.7 — Respaldo automático al cerrar

- Cada cierre normal de CodeCafe Atlas genera automáticamente un respaldo SQLite de la base activa.
- No solicita confirmación ni ubicación al usuario.
- El respaldo se guarda en la carpeta portátil `backups`, usando la nomenclatura fechada existente.
- Si ya existe un archivo con la misma fecha y hora, se agrega un consecutivo para no sobrescribir ningún respaldo.
- Después de crear el respaldo se muestra un aviso breve que se cierra automáticamente, sin requerir pulsar **Aceptar**.
- Si el respaldo falla, se muestra una advertencia temporal con el error y la aplicación termina sin ocultar el problema.
- La protección se ejecuta tanto al usar **Archivo → Salir** como al cerrar la ventana principal.
- No se modificaron la estructura ni el contenido de la base de datos, ni otros módulos funcionales.


## v0.24.8 — Separación mensual de cédulas por fecha del prestador

- El Separador PDF obtiene el mes exclusivamente de **Fecha reporte del prestador de servicio**.
- Se conserva la clasificación existente por **Tóner** y **Resto de fallas** —o por las categorías definidas para la sesión— y se agrega un nivel mensual superior.
- La estructura del ZIP para cédulas es `Año/Mes/Categoría/Folio.pdf`; por ejemplo, `2026/Julio/Tóner/REQ-12345.pdf`.
- La fecha puede extraerse del texto del PDF o mediante OCR local del campo específico, incluyendo valores manuscritos como `30-07-2026`.
- La tabla de revisión y la ventana de página completa permiten corregir la fecha con formato `DD-MM-AAAA` antes de exportar.
- Las cédulas cuya fecha no pueda identificarse se conservan dentro de `Año no identificado/Mes no identificado/Categoría/`, sin perder documentos.
- Otras fechas de la cédula no se utilizan para decidir el mes.
- No se modificaron los módulos restantes ni la base de datos.


## v1.0.0 — Rebranding a CodeCafe Atlas

- Nueva identidad pública: **CodeCafe Atlas**.
- Autoría visible: **Jaime Sánchez Sáenz**, CodeCafe.io, contacto@codecafe.io.
- Identificadores: `io.codecafe.atlas` y `CCA-JSS-2026`.
- Ejecutables oficiales: `CodeCafe-Atlas` y `CodeCafe-Atlas-Updater`.
- La base heredada `data/atlas.db` se conserva para evitar pérdida de información.
- Se crea de forma no destructiva la tabla `app_metadata`, preparada para espacios de trabajo personalizables.
- Los nombres internos heredados permanecen únicamente donde son necesarios para migración y compatibilidad.
- Los alias `CodeCafe-Atlas` y `CodeCafe-Atlas-Updater` se incluyen temporalmente para permitir la transición desde v0.24.8.


## v1.0.1 — Jerarquía Año/Mes/Categoría para cédulas

- La exportación de cédulas utiliza `Año/Mes/Categoría/Folio.pdf`.
- Ejemplo: `2026/07 Julio/Tóner/REQ-12345.pdf`.
- `Tóner`, `Resto de fallas` o cualquier filtro configurado se crea dentro del mes correspondiente.
- Las fechas no reconocidas se conservan en `Año no identificado/Mes no identificado/Categoría/`.
- No se modificaron la clasificación, el OCR, la base de datos ni otros módulos.



## v1.0.3 — Autoincremento seguro del ZIP

- El Separador inteligente no reemplaza archivos ZIP existentes.
- Si el nombre elegido está ocupado, Atlas genera automáticamente `_2`, `_3` y los números siguientes.
- Se conserva la opción de escribir manualmente cualquier nombre en el diálogo de guardado.
- La creación exclusiva evita sobrescrituras incluso ante una colisión de último momento.

## v1.0.2 — Formato automático de fecha en el Separador PDF

- Al escribir o pegar ocho dígitos en el campo de fecha, Atlas inserta automáticamente los guiones.
- Ejemplo: `09072026` se convierte en `09-07-2026`.
- El comportamiento se aplica tanto en la revisión ampliada como en la tabla de resultados.
- También se conserva la captura tradicional con guiones.
- No se modificaron la exportación, el OCR, la base de datos ni otros módulos.

## v1.0.4 — Logotipo oficial de CodeCafe Atlas

- Se incorpora el logotipo aprobado de **CodeCafe Atlas**, sin globo terráqueo.
- El panel de navegación muestra permanentemente la identidad visual oficial.
- La ventana **Ayuda → Acerca de** incluye el logotipo junto con la autoría y los identificadores del proyecto.
- La ventana principal y el actualizador utilizan el emblema Atlas como icono.
- Los recursos gráficos se incluyen en las compilaciones de Windows, Linux y macOS.
- No se modificaron la base de datos ni los módulos operativos.



## v1.0.6 — Reporte CSV dentro del ZIP

- Cada exportación del Separador inteligente incluye `reporte_exportacion.csv` en la raíz del ZIP.
- El reporte relaciona archivo de origen, página, folio o serie, categoría, fecha, método, confianza OCR y ruta del PDF exportado.
- El CSV utiliza UTF-8 con BOM para facilitar su apertura correcta en Excel.
- No cambia la clasificación, el OCR ni la jerarquía Año/Mes/Categoría.

## v1.0.5 — Guion automático en folios DGTI

- El campo **Número de serie / folio de servicio** inserta automáticamente el guion de la nomenclatura DGTI.
- Al escribir o pegar `R015422`, Atlas muestra `R-015422`.
- Las letras se convierten automáticamente a mayúsculas.
- Un folio ya escrito como `R-015422` se conserva sin duplicar el guion.
- El comportamiento se aplica tanto en la revisión ampliada como en la tabla de resultados.
- Los folios heredados o más complejos continúan aceptándose sin cambios destructivos.
- No se modificaron la base de datos, el OCR, la exportación ni otros módulos.


## v1.0.7 — Giro de vista y navegación por teclado

- Botón **↻ Girar 90°** en la revisión ampliada del Separador inteligente.
- Flechas **↑ / ↓** para recorrer los campos editables del panel de captura.
- El giro es solo visual y no altera los PDF de origen ni los archivos exportados.


## v1.0.8 — Estructura definitiva Año/Mes/Categoría

- El ZIP del Separador inteligente organiza las cédulas como `Año/Mes/Categoría/Folio.pdf`.
- El mes utiliza únicamente su nombre en español, sin prefijo numérico.
- Ejemplos: `2026/Mayo/Resto de fallas/R-008454.pdf` y `2026/Julio/Tóner/R-015422.pdf`.
- `reporte_exportacion.csv` permanece en la raíz del ZIP.
- Las fechas no identificadas se conservan en `Año no identificado/Mes no identificado/Categoría/`.
- No se modificaron el OCR, los folios, las categorías, la base de datos ni otros módulos.


## v1.0.9 — Historial del Separador inteligente

- Cada exportación correcta se registra automáticamente en un historial local persistente.
- El botón **Historial** muestra fecha y hora, tipo de documento, ruta del ZIP, cantidad de archivos de origen, páginas, identificadores y categorías.
- El historial conserva solamente metadatos; no crea copias adicionales de los PDF procesados.
- Los registros se guardan en `data/pdf_separator_history.json`, una ubicación preservada por el actualizador.
- Se conservan hasta 500 exportaciones recientes y el usuario puede borrar el historial sin eliminar los ZIP producidos.
- Si el historial no puede escribirse, el ZIP permanece válido y Atlas informa el problema sin perder la exportación.
- No se modificaron la base SQLite, el OCR, la clasificación, el CSV ni la estructura Año/Mes/Categoría.


## v1.0.10 — Administración de formatos

- Añade un módulo dedicado para consultar, crear, duplicar, modificar y eliminar formatos reutilizables.
- Los formatos se guardan en la tabla `service_formats` de la base SQLite activa.
- Cada formato puede precargar tipo de documento, validación, movimiento, falla reportada, diagnóstico, solución, observaciones, técnico y estado del equipo.
- El folio, la dependencia, el equipo, las fechas y los reportes permanecen como datos particulares de cada orden.
- Se incluyen como punto de partida los formatos Tóner, Vincular impresora y Escáner Ricoh.
- El módulo permite enviar un formato directamente a la captura de Órdenes de servicio.


## v1.0.11 — Biblioteca PDF cambia a Visor PDF

- El nombre visible del módulo cambia de **Biblioteca PDF** a **Visor PDF**.
- Se actualizan la navegación, el dashboard y el encabezado del módulo.
- Se conservan la indexación por carpetas, búsqueda, vista integrada, giro, zoom y apertura externa.
- El identificador interno `pdf_library` y el archivo `pdf_library_page.py` se mantienen para no romper configuraciones existentes.

## v1.0.12 — Folios únicos por sesión

- El Separador inteligente impide asignar el mismo folio a dos páginas durante una misma sesión.
- La validación se aplica tanto en la ventana ampliada de revisión como en la tabla de resultados.
- Los folios repetidos detectados automáticamente por OCR se descartan de la segunda entrada y esa página queda pendiente de revisión manual.
- El mensaje de advertencia indica el archivo y la página que ya utilizan el folio.
- La exportación se bloquea si por cualquier vía quedan folios duplicados sin corregir.
- El control usa únicamente los resultados cargados en memoria: al iniciar una sesión nueva, el mismo folio puede capturarse nuevamente.
- No se modifica el historial, la base de datos, los PDF de origen ni los ZIP previamente exportados.

## v1.0.13 — Revisión de PDF y nombre editable en Registro de contadores

- Cada documento del lote muestra el botón **Ver PDF** junto a su estado; las imágenes muestran **Ver imagen**.
- El botón abre la ventana ampliada ya existente para revisar la página, girarla, acercarla y corregir los contadores.
- La misma ventana incorpora el campo **Nombre del archivo**.
- Al cambiar el nombre de un PDF de varias páginas, el nombre visible se actualiza en todas sus páginas dentro del lote.
- El nombre corregido se utiliza en el historial y en los datos guardados o exportados posteriormente.
- Los caracteres no válidos para nombres de archivo se sustituyen de forma segura y la extensión original se conserva cuando se omite.
- Por seguridad del navegador integrado, esta edición cambia el nombre documental usado por Atlas; no renombra el archivo original almacenado en el disco.
- No se modificaron el OCR, los valores detectados, la base de datos ni otros módulos.



## v1.0.14 — Inserción exacta de contadores y reporte de discrepancias

- El Insertador de contadores relaciona reporte y hoja maestra exclusivamente mediante coincidencia exacta del número de serie normalizado.
- Se eliminaron las correcciones aproximadas por distancia de edición y cualquier intento de asociar series parecidas.
- Solo se modifican las columnas AK–AR dentro de las filas autorizadas de Torreón; la columna H y el resto de la hoja permanecen intactos.
- Para una serie exacta con al menos un contador numérico válido, las celdas realmente vacías de AK–AR sin dato compatible se completan con `0`.
- Los valores no numéricos, series inexistentes o duplicadas, fórmulas, diferencias entre fuentes y conflictos con valores existentes se documentan en `<copia>_DISCREPANCIAS.csv`.
- El CSV de discrepancias utiliza UTF-8 con BOM e identifica fuente, fila, serie, celda, valores comparados, acción y detalle.
- Si el reporte de discrepancias obligatorio no puede guardarse, la copia producida se elimina para evitar una entrega incompleta.
- El separador PDF, el Registro de contadores y los demás módulos no fueron modificados.

## v1.0.16 — Detección de duplicados y eliminación en Visor PDF

El Visor PDF puede analizar la carpeta seleccionada para localizar copias exactas por contenido mediante tamaño y SHA-256. Los resultados se agrupan y pueden filtrarse para revisar cada copia. Cualquier PDF seleccionado puede moverse a la papelera o eliminarse permanentemente después de una confirmación explícita.

## v1.0.16 — Corrección de arranque

- Corrige `NameError: STATUS_VALUE is not defined` al construir el Insertador inteligente de contadores.
- Añade una validación estática específica antes de compilar.
- No modifica datos ni comportamiento funcional de los módulos.


## v1.0.17 — Campo único para serie y nombre PDF

En la revisión del Registro de contadores se eliminó el campo independiente
**Nombre del archivo**. El único campo editable es **Número de serie / equipo**.
Atlas usa ese mismo valor como número de serie y como nombre lógico del
documento, agregando `.pdf` internamente sin mostrar la extensión en el campo.
El cambio se aplica solo al documento/página revisado y no se propaga a otras
páginas del lote.

## v1.0.18 — Serie editable directamente en el lote

La columna **Número de serie** del lote del Registro de contadores puede editarse sin abrir la ventana **Ver PDF**. La corrección actualiza la entrada que se guardará, conserva un solo campo de identificación y permite confirmar con Enter o cancelar con Escape. No se modificaron el OCR, los valores de contadores ni otros módulos.



## v1.0.19 — Ciudad y estado editables en la cédula

- Los campos Ciudad y Estado de la dependencia pueden editarse directamente en el Generador de orden de servicio / cédula.
- Al guardar el registro o generar la cédula, los valores se actualizan en la ubicación asociada a la dependencia dentro de la base del Directorio.
- La vista previa y el documento generado usan inmediatamente los valores editados.
- No se modificaron otros datos de la dependencia ni otros módulos.

## v1.0.24 — Restauración completa del Directorio

El Directorio vuelve a mostrar directamente en cada dependencia todos los campos existentes de ubicación y contacto, sin obligar a abrir la ventana de edición. No se añadieron columnas a la base ni se modificaron otros módulos.
