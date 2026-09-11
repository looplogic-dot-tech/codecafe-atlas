from __future__ import annotations

import ast
import sqlite3
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PKG = ROOT / 'codecafe_atlas'


def require(path: Path, *fragments: str) -> None:
    text = path.read_text(encoding='utf-8')
    missing = [fragment for fragment in fragments if fragment not in text]
    if missing:
        raise SystemExit(f'ERROR {path.name}: faltan: {missing}')


def require_methods(path: Path, class_name: str, methods: set[str]) -> None:
    tree = ast.parse(path.read_text(encoding='utf-8'))
    cls = next((n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name), None)
    if cls is None:
        raise SystemExit(f'ERROR {path.name}: falta clase {class_name}')
    available = {n.name for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    missing = sorted(methods - available)
    if missing:
        raise SystemExit(f'ERROR {path.name}: faltan métodos {missing}')

# Directorio: última intención conocida (v1.0.21 -> v1.0.24.14 -> v1.0.24.17)
require(PKG/'directory_page.py',
        'Ver información completa', 'Usuario del equipo', 'assigned_user',
        'Editar edificio', '＋ Añadir edificio', 'Dirección heredada del edificio',
        'similar_buildings', 'similar_dependencies')
# Directorio: selector editable de edificios existentes + alta nueva + protección de similitud.
directory_text=(PKG/'directory_page.py').read_text(encoding='utf-8')
for fragment in (
    'building_combo = QComboBox()',
    'building_combo.setEditable(True)',
    '＋ Nuevo edificio',
    'self.database.similar_buildings(name)',
    'Posible edificio duplicado',
    'Selecciona un edificio existente o escribe uno nuevo',
):
    if fragment not in directory_text:
        raise SystemExit(f'ERROR Directorio: falta flujo protegido de edificios ({fragment})')

# Juzgado/Tribunal pueden persistir por compatibilidad, pero no deben estar como renglones editables.
for forbidden_ui in ('form.addRow("Juzgado"', 'form.addRow("Tribunal"'):
    if forbidden_ui in directory_text:
        raise SystemExit(f'ERROR Directorio: reapareció campo retirado {forbidden_ui}')

# Inventario: persistencia, duplicados, revisión continua, numeración, total y orden natural.
require(PKG/'inventory_page.py',
        'Revisar series duplicadas', 'Total de equipos:', '_sort_value', '_sort_key',
        '_sorted_rows', 'setSortIndicator', 'equipment_duplicate_groups',
        'merge_duplicate_equipment', 'row_index + 1')
require_methods(PKG/'inventory_page.py', 'InventoryPage',
                {'save','review_duplicates','_sort_value','_sort_key','_sorted_rows'})

# Administración de datos: preview, reemplazo filtrado, reset, backup y Excel editable.
require(PKG/'data_page.py',
        'Previsualizar o reemplazar desde otra base', 'Exportar base a Excel editable',
        'Restablecer Atlas a una base vacía', 'import_preview',
        'replace_with_filtered_database', 'reset_to_empty', 'export_editable_excel')

# Exportación editable completa y con lenguaje de negocio.
require(PKG/'editable_excel_export.py',
        'Nombre del edificio', 'Calle o avenida', 'Número exterior', 'Colonia', 'Código postal', 'Ciudad', 'Estado',
        'Piso', 'Dependencia, juzgado, tribunal u oficina', 'CTA / encargado de la dependencia', 'Oficina / grupo de trabajo', 'Usuario del equipo',
        'Marca del equipo', 'Modelo del equipo', 'Número de serie', 'Número de inventario',
        'Dirección IP', 'Nombre de red / hostname', 'Estado del equipo', 'Observaciones del equipo')

# Registro de contadores: última UX documentada (v1.0.17/18 + v1.0.24.13).
counter_html=(ROOT/'modules/counter_registry/index.html').read_text(encoding='utf-8')
for fragment in ('Datos comunes del reporte Excel','Dependencia','Notas','Mes que aparecerá en los encabezados',
                 'Ver PDF','Ver imagen','batch-serial-input',"event.key === 'Enter'","event.key === 'Escape'",
                 'Número de serie / equipo','vendor/pdfjs/pdf.js','vendor/pdfjs/pdf.worker.js',
                 'PDF_STANDARD_FONT_URL','describePdfOpenError',
                 'MAX_PDF_CACHE_DOCUMENTS = 2','trimPdfCache()',
                 'releaseAllPdfDocuments()','await document.destroy()'):
    if fragment not in counter_html:
        raise SystemExit(f'ERROR Registro de contadores: falta {fragment}')
for remote_pdf_dependency in ('cdnjs.cloudflare.com/ajax/libs/pdf.js', 'pdf.worker.min.js'):
    if remote_pdf_dependency in counter_html:
        raise SystemExit(
            f'ERROR Registro de contadores: conserva dependencia PDF remota ({remote_pdf_dependency})'
        )
for relative_asset in (
    'modules/counter_registry/vendor/pdfjs/pdf.js',
    'modules/counter_registry/vendor/pdfjs/pdf.worker.js',
    'modules/counter_registry/vendor/pdfjs/LICENSE',
    'modules/counter_registry/vendor/pdfjs/standard_fonts/LiberationSans-Regular.ttf',
):
    if not (ROOT / relative_asset).is_file():
        raise SystemExit(f'ERROR Registro de contadores: falta recurso PDF local {relative_asset}')
for obsolete in ('ID inicial','Descripción de equipo','Perfil del equipo'):
    # Text elsewhere in historical help is acceptable only if it is not an active input label.
    if f'<label for=' in counter_html and f'>{obsolete}<' in counter_html:
        raise SystemExit(f'ERROR Registro de contadores: reapareció campo visible {obsolete}')

# Insertador: destinos seleccionables, altas protegidas y estado operativo derivado.
insert_text=(PKG/'counter_inserter_engine.py').read_text(encoding='utf-8')
insert_page_text=(PKG/'counter_inserter_page.py').read_text(encoding='utf-8')
for fragment in ('def configure_target_range', 'expected_last = first + 7',
                 'TARGET_BY_KEY.clear()', 'TARGET_COLS.clear()', 'TARGET_LOCALITY = "Torreón"',
                 'No existe una coincidencia exacta', '_DISCREPANCIAS.csv',
                 'column_number', 'target_range_label', 'def read_atlas_counter_database',
                 'mode=ro', 'report_tables: Optional[list[TableData]]',
                 'def similar_master_serials', 'posible_serie_mal_escrita',
                 'create_missing_rows', 'creates_master_row',
                 'def status_header_score', 'def status_updates',
                 'STATUS_VALUE = "En Operación"'):
    if fragment not in insert_text:
        raise SystemExit(f'ERROR Insertador: falta {fragment}')
for fragment in ('Mapeo destino:', 'Serie en hoja maestra:', 'self.target_range_edit',
                 'self.master_serial_edit', 'master_serial_spec=master_serial_spec',
                 'source_spec="AUTO"', 'Base de datos de Atlas',
                 'read_atlas_counter_database(database_path())',
                 'Añadir series faltantes a la copia',
                 'Autorizar series parecidas ya revisadas',
                 'main_splitter = QSplitter(Qt.Orientation.Horizontal)',
                 'main_splitter.addWidget(left)', 'main_splitter.addWidget(right)',
                 'right_layout.addWidget(splitter, 1)',
                 'counter_inserter/main_splitter',
                 'Corregir serie seleccionada…', 'self._serial_overrides',
                 'self.table.itemChanged.connect(self._serial_item_changed)',
                 'serial_overrides=serial_overrides'):
    if fragment not in insert_page_text:
        raise SystemExit(f'ERROR Insertador seleccionable: falta {fragment}')
for fragment in ('def apply_serial_overrides(', 'serial_overrides: Optional[dict[str, str]]',
                 'report = apply_serial_overrides(report, mapping, serial_overrides)',
                 'def equipment_location_header_score(', 'def source_dependency_column(',
                 'def _equipment_location_decision(', 'def location_updates(',
                 'location_updates = analysis.location_updates()',
                 'UBICACION_REEMPLAZADA'):
    if fragment not in insert_text:
        raise SystemExit(f'ERROR Insertador editable: falta {fragment}')
for fragment in ('Completar Ubicación de Equipo desde la dependencia de Atlas',
                 'Reemplazar también ubicaciones existentes',
                 'location_mode=location_mode', 'decision.location_action',
                 'counts.get("location_updates", 0)'):
    if fragment not in insert_page_text:
        raise SystemExit(f'ERROR Insertador ubicación: falta {fragment}')
if 'celdas en H y AK–AR' in insert_text or 'H se estableció como' in insert_text:
    raise SystemExit('ERROR Insertador: quedó texto/flujo obsoleto de escritura en H')

# Separador: categorías/fecha, folios, revisión, eliminación continua, historial, CSV y no-overwrite.
require(PKG/'pdf_page.py',
        'Eliminar entrada', 'def delete_current', 'save_and_next',
        'Fecha reporte del prestador de servicio', 'Año no identificado', 'Mes no identificado',
        'Folio duplicado en esta sesión', 'EXPORT_REPORT_FILENAME', 'Historial',
        'next_available_path', '↻ Girar 90°')
require_methods(PKG/'pdf_page.py','ReviewDialog',{'delete_current','save_and_next','rotate_clockwise','eventFilter'})

# Visor PDF: index/búsqueda/visor + duplicados exactos y eliminación segura.
require(PKG/'pdf_library_page.py',
        'Visor PDF','Detectar duplicados','Mostrar solo duplicados','Mover a la papelera',
        'Eliminar permanentemente','find_exact_duplicate_groups')
require(PKG/'pdf_duplicate_tools.py','sha256','find_exact_duplicate_groups')

# Órdenes de servicio: equipo existente/nuevo, ciudad/estado editables, formatos, preview,
# carpeta, recarga y configuración de plantilla v1.0.24.16.
require(PKG/'service_order_page.py',
        'Actualizar datos','Cargar / configurar plantilla Excel','Restaurar plantilla incluida','Buscar / abrir carpeta',
        'Equipo nuevo','Ciudad','Estado','sync_dependency_city_state','Vista previa de cédula',
        'equipment_search_changed','ensure_initial_template_configuration')
require(PKG/'service_template_config.py', 'cell_map','field_mappings','required_placeholders','＋ Añadir campo','Eliminar fila seleccionada','Cargar plantilla Excel propia','Guardar configuración')
require(PKG/'service_order_page.py','service_template_config.json','active_service_template.xlsx','Reporte DGTI es también el folio')

# Administración de formatos: biblioteca primero; editor solo tras selección/nuevo.
require(PKG/'formats_page.py',
        'Biblioteca de plantillas y formatos','Nuevo formato','Selecciona un formato para ver o editar su configuración',
        'Usar en orden de servicio','Guardar formato')

# Homologación actual: esquema canónico, todas las entidades, no "Mantener ambos", backup/tx/validaciones.
require(PKG/'sync_compare_page.py','Homologar base local','Conservar local','Usar externo','Exportar reporte CSV')
sync_text=(PKG/'sync_engine.py').read_text(encoding='utf-8')
for fragment in ('atlas_buildings','atlas_people','atlas_dependencies','atlas_offices','atlas_dependency_people',
                 'atlas_equipment','atlas_counter_readings','atlas_service_orders','service_formats',
                 'PRAGMA integrity_check','PRAGMA foreign_key_check'):
    if fragment not in sync_text:
        raise SystemExit(f'ERROR Homologación: falta {fragment}')
if 'Mantener ambos' in (PKG/'sync_compare_page.py').read_text(encoding='utf-8'):
    raise SystemExit('ERROR Homologación: reapareció Mantener ambos')

# DB: identidad de equipo, duplicados organizacionales, historial y compatibilidad.
require(PKG/'database.py',
        'serial_number','equipment_duplicate_groups','merge_duplicate_equipment',
        'similar_buildings','similar_dependencies','save_counter_records',
        'import_preview','replace_with_filtered_database','reset_to_empty')

# Dashboard, backups y updater.
require(PKG/'home_page.py','Personalizar dashboard','Restaurar fondo predeterminado')
require(PKG/'main_window.py','closeEvent','self.database.backup(backups_dir())','Administración de formatos','homologation_page=self.sync_compare_page')
require(PKG/'data_page.py','QTabWidget','Base de datos','Homologación','show_homologation')
require(PKG/'counter_inserter_engine.py','equipment without a reading','ubicacion_lista','existing == source_location')
require(PKG/'updater.py','hashlib.sha256','sha256')

# Base nueva debe estar realmente vacía y ser íntegra.
from codecafe_atlas.database import Database
with tempfile.TemporaryDirectory(prefix='atlas_full_recovery_') as td:
    dbp=Path(td)/'atlas.db'
    db=Database(dbp)
    con=sqlite3.connect(dbp)
    try:
        if con.execute('PRAGMA integrity_check').fetchone()[0].lower()!='ok':
            raise SystemExit('ERROR DB: integrity_check falló')
        if list(con.execute('PRAGMA foreign_key_check')):
            raise SystemExit('ERROR DB: foreign keys rotas')
        for table in ('atlas_buildings','atlas_dependencies','atlas_offices','atlas_people','atlas_equipment',
                      'atlas_counter_readings','atlas_service_orders','service_formats'):
            count=con.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
            if count != 0:
                raise SystemExit(f'ERROR DB nueva: {table} contiene {count} registros')
    finally:
        con.close()


# Approved native folder opener must remain wired into service orders.
platform_open_path = ROOT / "codecafe_atlas" / "platform_open.py"
service_order_path = ROOT / "codecafe_atlas" / "service_order_page.py"
if not platform_open_path.is_file():
    raise SystemExit("ERROR Full Function: falta codecafe_atlas/platform_open.py")
platform_open_text = platform_open_path.read_text(encoding="utf-8")
service_order_text = service_order_path.read_text(encoding="utf-8")
for fragment in ("def open_directory_native", "dolphin", "--new-window", "xdg-open", "LD_LIBRARY_PATH_ORIG", "_external_process_environment"):
    if fragment not in platform_open_text:
        raise SystemExit(f"ERROR Full Function: opener de carpetas incompleto ({fragment})")
for fragment in ("Buscar / abrir carpeta", "open_directory_native(folder)", "opened, diagnostic"):
    if fragment not in service_order_text:
        raise SystemExit(f"ERROR Full Function: botón abrir carpeta perdió integración ({fragment})")

print('FULL FUNCTION RECOVERY VALIDATION: PASS')

# v1.0.24.24: reproducible/offline build-system regression guards.
bootstrap_path = ROOT / "bootstrap_dependencies.py"
windows_release_path = ROOT / "build_windows_release.py"
if not bootstrap_path.is_file():
    raise SystemExit("ERROR Build v1.0.24.24: falta bootstrap_dependencies.py.")
if not windows_release_path.is_file():
    raise SystemExit("ERROR Build v1.0.24.24: falta build_windows_release.py.")
bootstrap_text = bootstrap_path.read_text(encoding="utf-8")
for fragment in ("packages", "--no-index", "--find-links", '"download"', "resolved-requirements.txt", "--offline"):
    if fragment not in bootstrap_text:
        raise SystemExit(f"ERROR Build v1.0.24.24: bootstrap sin protección requerida ({fragment}).")
windows_build_text = (ROOT / "build_windows.bat").read_text(encoding="utf-8")
bootstrap_index = windows_build_text.find("bootstrap_dependencies.py")
validator_index = windows_build_text.find("validate_public_identity.py")
if bootstrap_index < 0 or validator_index < 0 or bootstrap_index > validator_index:
    raise SystemExit("ERROR Build v1.0.24.24: Windows debe preparar dependencias antes de validar.")
for fragment in ("build_windows_release.py", "1.0.24.34", "release\\CodeCafe_Atlas_v1.0.24.34_Windows_x64.zip"):
    if fragment not in windows_build_text:
        raise SystemExit(f"ERROR Build v1.0.24.24: build Windows incompleto ({fragment}).")
windows_release_text = windows_release_path.read_text(encoding="utf-8")
for fragment in ("LOCALAPPDATA", "CodeCafeAtlasBuild", "smoke_test(main_exe)", "Portable ZIP"):
    if fragment not in windows_release_text:
        raise SystemExit(f"ERROR Build v1.0.24.24: falta mitigación Windows ({fragment}).")
for build_name in ("build_linux.sh", "build_macos.sh"):
    build_text = (ROOT / build_name).read_text(encoding="utf-8")
    if "bootstrap_dependencies.py" not in build_text:
        raise SystemExit(f"ERROR Build v1.0.24.24: {build_name} no usa cache de dependencias.")
print("BUILD REPRODUCIBILITY VALIDATION: PASS")

require(PKG/'platform_open.py','open_file_native','kioclient6','gio','xdg-open','libreoffice')
require(PKG/'service_order_page.py','open_file_native(output)','open_file_native(path)')


# SERVICE ORDER REMOVED PRESET UI STARTUP GUARD
# v1.0.24.25 removed the saved-format selector from ServiceOrderPage. No startup
# wiring may reference the removed refresh_saved_formats() method.
_main_window = (ROOT / "codecafe_atlas" / "main_window.py").read_text(encoding="utf-8")
_service_order = (ROOT / "codecafe_atlas" / "service_order_page.py").read_text(encoding="utf-8")
if "refresh_saved_formats" in _main_window:
    raise SystemExit("ERROR: main_window.py todavía referencia refresh_saved_formats eliminado.")
if "def refresh_saved_formats" in _service_order:
    raise SystemExit("ERROR: reapareció refresh_saved_formats pese a eliminarse el selector redundante.")
print("SERVICE ORDER REMOVED PRESET UI STARTUP GUARD: PASS")

# SERVICE ORDER TEMPLATE/TIME REGRESSION GUARD (v1.0.24.26+)
_generator = (ROOT / "codecafe_atlas" / "service_document_generator.py").read_text(encoding="utf-8")
if 'alignment.wrapText = False' in _generator:
    raise SystemExit("ERROR: Atlas vuelve a desactivar el ajuste de A53/H53.")
for _fragment in ('setDisplayFormat("HH:mm:ss")', 'toString("HH:mm:ss")', '"hh:mm:ss AP"', '"HH:mm"'):
    if _fragment not in _service_order:
        raise SystemExit(f"ERROR: formato horario o compatibilidad incompleta ({_fragment}).")
print("SERVICE ORDER TEMPLATE/TIME REGRESSION GUARD: PASS")

# v1.0.24.27: mejoras aisladas sobre la base madura.
for _path in (
    ROOT / "codecafe_atlas" / "service_quick_templates.py",
    ROOT / "codecafe_atlas" / "technical_library_page.py",
    ROOT / "codecafe_atlas" / "auxiliary_tools_page.py",
):
    if not _path.is_file():
        raise SystemExit(f"ERROR v1.0.24.27: falta {_path.name}.")

_quick_templates = (ROOT / "codecafe_atlas" / "service_quick_templates.py").read_text(encoding="utf-8")
for _fragment in (
    "DEFAULT_QUICK_TEMPLATES", "load_quick_templates", "save_quick_templates",
    "QuickTemplateEditorDialog", "Eliminar plantilla rápida", "Entrada manual",
):
    if _fragment not in _quick_templates:
        raise SystemExit(f"ERROR Plantillas rápidas: falta {_fragment}.")
for _fragment in (
    "Editar plantillas rápidas…", "refresh_quick_templates", "edit_quick_templates",
):
    if _fragment not in _service_order:
        raise SystemExit(f"ERROR Orden de servicio: editor rápido incompleto ({_fragment}).")

_pdf_library = (ROOT / "codecafe_atlas" / "pdf_library_page.py").read_text(encoding="utf-8")
for _fragment in (
    "Renombrar PDF…", "rename_selected_pdf", "QKeySequence(Qt.Key.Key_F2)",
    "Atlas no sobrescribió ningún archivo", "path.rename(new_path)",
):
    if _fragment not in _pdf_library:
        raise SystemExit(f"ERROR Visor PDF: renombrado incompleto ({_fragment}).")

_technical_library = (ROOT / "codecafe_atlas" / "technical_library_page.py").read_text(encoding="utf-8")
for _fragment in (
    "class TechnicalLibraryPage", "technical_library_settings.json",
    "Seleccionar carpeta raíz…", "SUPPORTED_EXTENSIONS", "rglob",
):
    if _fragment not in _technical_library:
        raise SystemExit(f"ERROR Biblioteca técnica: falta {_fragment}.")

_auxiliary_tools = (ROOT / "codecafe_atlas" / "auxiliary_tools_page.py").read_text(encoding="utf-8")
for _fragment in (
    "class AuxiliaryToolsPage", "Separador de PDFs por dependencia",
    "dependency_pdf_separator", '"--database", str(data_dir() / "atlas.db")',
    "Atlas Data Bridge", "Comparador de hojas de cálculo",
    "auxiliary_tools_settings.json", "QProcess.startDetached", '"/bin/bash"',
):
    if _fragment not in _auxiliary_tools:
        raise SystemExit(f"ERROR Herramientas auxiliares: falta {_fragment}.")

for _fragment in (
    '("technical_library", "Biblioteca técnica", self.technical_library_page)',
    '("auxiliary_tools", "Herramientas auxiliares", self.auxiliary_tools_page)',
):
    if _fragment not in _main_window:
        raise SystemExit(f"ERROR Navegación v1.0.24.27: falta {_fragment}.")
print("V1.0.24.27 OPERATIONAL IMPROVEMENTS VALIDATION: PASS")

# v1.0.24.28: keyboard-first counter review workflow restored.
_counter_registry = (ROOT / "modules" / "counter_registry" / "index.html").read_text(encoding="utf-8")
for _fragment in (
    "const counterReviewEditableFieldIds = [",
    "function focusAdjacentCounterReviewField(currentField, direction)",
    "function handleCounterReviewKeyboard(event)",
    "event.key === 'ArrowUp' || event.key === 'ArrowDown'",
    "void applyCounterReviewAndNext();",
    "if (counterReview.navigating) return;",
):
    if _fragment not in _counter_registry:
        raise SystemExit(f"ERROR Navegación de contadores v1.0.24.28: falta {_fragment}.")
print("V1.0.24.28 COUNTER KEYBOARD NAVIGATION VALIDATION: PASS")

# v1.0.24.29: explicit bulk registration of serials discovered by counters.
_counter_bridge = (ROOT / "codecafe_atlas" / "counter_registry_page.py").read_text(encoding="utf-8")
_database_source = (ROOT / "codecafe_atlas" / "database.py").read_text(encoding="utf-8")
for _fragment in (
    "def saveRecordsWithRegistration(self, payload: str)",
    'prompt.setWindowTitle("Equipos no registrados")',
    'setText("Registrar y guardar")',
    'setText("Guardar solo lecturas")',
    "self.equipmentChanged.emit(changed)",
):
    if _fragment not in _counter_bridge:
        raise SystemExit(f"ERROR Alta masiva v1.0.24.29: falta {_fragment}.")
for _fragment in (
    "def missing_counter_equipment(",
    "register_missing: bool = False",
    '"Registrado desde un lote del Registro de contadores."',
    "def _link_unassigned_counter_readings(",
):
    if _fragment not in _database_source:
        raise SystemExit(f"ERROR Alta masiva v1.0.24.29: falta {_fragment}.")
for _fragment in (
    "saveRecordsWithRegistration",
    "dependencyOption?.dataset?.dependencyId",
    "databaseResult.cancelled",
    "equipmentCreated",
):
    if _fragment not in _counter_registry:
        raise SystemExit(f"ERROR Flujo HTML de alta masiva v1.0.24.29: falta {_fragment}.")
print("V1.0.24.29 BULK COUNTER EQUIPMENT REGISTRATION GUARD: PASS")

# v1.0.24.30: capture hostname from HP reports without overwriting inventory.
for _fragment in (
    "const HOSTNAME_CROP =",
    'id="hostnameId"',
    'id="counterReviewHostname"',
    "function parseHostname(text)",
    "function cleanHostname(value)",
    "getHostnameCropForOcr",
    "hostnameConflicts",
):
    if _fragment not in _counter_registry:
        raise SystemExit(f"ERROR Hostname v1.0.24.30: falta {_fragment}.")
for _fragment in (
    "def _equipment_for_hostname(",
    "hostnames_completed",
    "hostnames_preserved",
    "hostname_conflicts",
    "UPDATE atlas_equipment SET hostname=?",
):
    if _fragment not in _database_source:
        raise SystemExit(f"ERROR Persistencia hostname v1.0.24.30: falta {_fragment}.")
for _fragment in ("equipmentChanged = Signal(int)", "self.equipmentChanged.emit(changed)"):
    if _fragment not in _counter_bridge:
        raise SystemExit(f"ERROR Actualización hostname v1.0.24.30: falta {_fragment}.")
print("V1.0.24.30 COUNTER HOSTNAME COMPLETION GUARD: PASS")

# v1.0.24.31: bilingual agreement acceptance without touching operational data.
_use_agreement_path = ROOT / "codecafe_atlas" / "use_agreement.py"
if not _use_agreement_path.is_file():
    raise SystemExit("ERROR Licencia v1.0.24.31: falta use_agreement.py.")
_use_agreement = _use_agreement_path.read_text(encoding="utf-8")
for _fragment in (
    'AGREEMENT_VERSION = "2026-08-29.1"',
    "AGREEMENT_ES =",
    "AGREEMENT_EN =",
    "def agreement_hash()",
    'data_dir() / "license_acceptances.json"',
    "def current_user_has_accepted()",
    "def ensure_use_agreement(parent=None)",
    '"agreement_sha256": agreement_hash()',
    '"accepted_at_utc": datetime.now(timezone.utc).isoformat()',
    "El Licenciatario conserva la propiedad y el control de los datos operativos",
    "no solicitó, encargó ni comisionó originalmente la creación de Atlas",
    "did not originally request, commission, or direct the creation of Atlas",
    "remains the property of Licensor",
    "no autoriza al Licenciante a borrar, cifrar, apropiarse o alterar",
):
    if _fragment not in _use_agreement:
        raise SystemExit(f"ERROR Licencia v1.0.24.31: falta {_fragment}.")
for _fragment in (
    "from .use_agreement import ensure_use_agreement, show_use_agreement",
    'QAction("Licencia de uso / Software License", self)',
    "if not ensure_use_agreement():",
):
    if _fragment not in _main_window:
        raise SystemExit(f"ERROR Integración licencia v1.0.24.31: falta {_fragment}.")
print("V1.0.24.31 BILINGUAL USE AGREEMENT GUARD: PASS")

# v1.0.24.33: bounded-memory and responsive large-batch PDF separation.
_pdf_source = (ROOT / "codecafe_atlas" / "pdf_page.py").read_text(encoding="utf-8")
for _fragment in (
    "def recognize_image(image: Image.Image, configs: tuple[str, ...]) -> str:",
    "image.close()",
    "page_batch_ready = Signal(object)",
    "if len(pending_results) >= 8:",
    "type=Qt.ConnectionType.BlockingQueuedConnection",
    "self.table.setUpdatesEnabled(False)",
    "rows_height = row_count * 108",
):
    if _fragment not in _pdf_source:
        raise SystemExit(f"ERROR Separador v1.0.24.33: falta {_fragment}.")
print("V1.0.24.33 LARGE PDF BATCH GUARD: PASS")

# SERVICE ORDER COMPLETE CLEAR-FORM REGRESSION GUARD
# Nuevo / limpiar must reset every user-facing field group, not only service notes.
import ast as _ast
_service_source = (ROOT / "codecafe_atlas" / "service_order_page.py").read_text(encoding="utf-8")
_tree = _ast.parse(_service_source)
_clear_node = None
for _node in _ast.walk(_tree):
    if isinstance(_node, (_ast.FunctionDef, _ast.AsyncFunctionDef)) and _node.name == "clear_form":
        _clear_node = _node
        break
if _clear_node is None:
    raise SystemExit("ERROR: falta ServiceOrderPage.clear_form().")
_clear_text = _ast.get_source_segment(_service_source, _clear_node) or ""
for _fragment in (
    "self.document_type", "self.dgti_report.clear()", "self.provider_report.clear()",
    "self.output_folder.setText(self.last_output_folder or \"\")", "self.dependency_filter.clear()",
    "self.dependency.setCurrentIndex(-1)", "self.auto_dependency_name",
    "self.auto_city", "self.auto_state", "self.responsible_name.clear()",
    "self.validator_name.clear()", "self.validator_role.clear()",
    "self.validator_phone.clear()", "self.equipment_filter.clear()",
    "self.equipment.setCurrentIndex(-1)", "self._equipment_detail_widgets()",
    "self.reported_issue.clear()", "self.diagnosis.clear()",
    "self.solution.clear()", "self.service_notes.clear()",
    "self.technician_name.clear()",
):
    if _fragment not in _clear_text:
        raise SystemExit(f"ERROR: Nuevo / limpiar no reinicia el formulario completo ({_fragment}).")
print("SERVICE ORDER COMPLETE CLEAR-FORM VALIDATION: PASS")

# v1.0.24.45: a new service order starts at the top and counter review uses
# the largest available workspace without losing its approved navigation.
for _fragment in (
    "self.form_scroll = QScrollArea()",
    "self._scroll_form_to_top()",
    "vertical.setValue(vertical.minimum())",
    "QTimer.singleShot(0, reset_scrollbars)",
    "self.dgti_report.setFocus()",
):
    if _fragment not in _service_source:
        raise SystemExit(f"ERROR Órdenes v1.0.24.45: falta {_fragment}.")
_counter_page_source = (ROOT / "codecafe_atlas" / "counter_registry_page.py").read_text(encoding="utf-8")
_counter_html_source = (ROOT / "modules" / "counter_registry" / "index.html").read_text(encoding="utf-8")
for _fragment in (
    "reviewLargeModeRequested = Signal(bool)",
    "def setReviewLargeMode(self, active: bool)",
    "window.showMaximized()",
    "window.setWindowState(previous)",
):
    if _fragment not in _counter_page_source:
        raise SystemExit(f"ERROR Revisión v1.0.24.45: falta {_fragment}.")
for _fragment in (
    "width: 100vw;", "height: 100vh;",
    "bridgeCall('setReviewLargeMode', true)",
    "bridgeCall('setReviewLargeMode', false)",
    "handleCounterReviewKeyboard", "fitCounterReview",
):
    if _fragment not in _counter_html_source:
        raise SystemExit(f"ERROR Visor v1.0.24.45: falta {_fragment}.")
print("V1.0.24.45 SERVICE TOP / LARGE COUNTER REVIEW GUARD: PASS")

# v1.0.24.46: saved counter readings remain correctable and suspected serial
# typos are warnings that require a user decision.
for _fragment in (
    "def _serial_edit_distance(",
    "def counter_serial_suggestions(",
    "def update_counter_record(",
    "atlas_counter_reading_edits",
    "linked_to_inventory",
):
    if _fragment not in _database_source:
        raise SystemExit(f"ERROR Historial v1.0.24.46: falta {_fragment}.")
for _fragment in (
    "def editRecord(self, record_uid: str)",
    "Posibles series mal escritas",
    "Regresar y corregir",
    "Guardar exactamente así",
):
    if _fragment not in _counter_page_source:
        raise SystemExit(f"ERROR Advertencia v1.0.24.46: falta {_fragment}.")
for _fragment in (
    "editRecordInDatabase(recordId)",
    "editButton.textContent = 'Editar'",
    "bridgeCall('editRecord'",
):
    if _fragment not in _counter_html_source:
        raise SystemExit(f"ERROR Interfaz historial v1.0.24.46: falta {_fragment}.")
print("V1.0.24.46 EDITABLE COUNTER HISTORY / TYPO WARNING GUARD: PASS")

# v1.0.24.47: history actions must be placed beside the date, not beyond all
# wide counter columns where they disappear from the initial viewport.
_history_header = _counter_html_source[
    _counter_html_source.index("<h2>Historial de contadores</h2>"):
    _counter_html_source.index('<tbody id="historyBody">')
]
if not (
    _history_header.index("<th>Fecha</th>")
    < _history_header.index("<th>Acción</th>")
    < _history_header.index("<th>Equipo / serie</th>")
):
    raise SystemExit("ERROR Historial v1.0.24.47: Acción no está junto a Fecha.")
for _fragment in (
    ".history-actions { white-space: nowrap;",
    "action.className = 'history-actions'",
    "if (index === 0) row.appendChild(action)",
):
    if _fragment not in _counter_html_source:
        raise SystemExit(f"ERROR Historial visible v1.0.24.47: falta {_fragment}.")
print("V1.0.24.47 VISIBLE COUNTER HISTORY ACTIONS GUARD: PASS")

# v1.0.24.48: historical readings and unique equipment are different metrics.
for _fragment in (
    'id="recordCount">0 lecturas históricas',
    'id="equipmentCount">0 equipos únicos',
    'id="unlinkedCount"',
    "function normalizedHistorySerial(value)",
    "function historySummary()",
    "function updateHistorySummary()",
    "historyDatabaseStatusText()",
):
    if _fragment not in _counter_html_source:
        raise SystemExit(f"ERROR Resumen historial v1.0.24.48: falta {_fragment}.")
if '"equipmentId": row["equipment_id"]' not in _database_source:
    raise SystemExit("ERROR Resumen historial v1.0.24.48: falta vínculo con Inventario.")
print("V1.0.24.48 COUNTER READINGS / UNIQUE EQUIPMENT SUMMARY GUARD: PASS")

# v1.0.24.49: unlinked series must be immediately visible and filterable.
for _fragment in (
    "history-unlinked-row",
    "unlinked-badge",
    "history-filter-button",
    "function unlinkedHistorySerials()",
    "showOnlyUnlinkedHistory",
    "badge.textContent = 'Sin vincular'",
    "$('unlinkedCount').addEventListener('click'",
):
    if _fragment not in _counter_html_source:
        raise SystemExit(f"ERROR Series sin vincular v1.0.24.49: falta {_fragment}.")
print("V1.0.24.49 UNLINKED COUNTER SERIES HIGHLIGHT / FILTER GUARD: PASS")
