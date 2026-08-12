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
                 'Número de serie / equipo'):
    if fragment not in counter_html:
        raise SystemExit(f'ERROR Registro de contadores: falta {fragment}')
for obsolete in ('ID inicial','Descripción de equipo','Perfil del equipo'):
    # Text elsewhere in historical help is acceptable only if it is not an active input label.
    if f'<label for=' in counter_html and f'>{obsolete}<' in counter_html:
        raise SystemExit(f'ERROR Registro de contadores: reapareció campo visible {obsolete}')

# Insertador: última intención v1.0.14 gana sobre v1.0.5: solo AK:AR, serie exacta, H intacta.
insert_text=(PKG/'counter_inserter_engine.py').read_text(encoding='utf-8')
for fragment in ('TARGET_FIRST_COL = 37', 'TARGET_LAST_COL = 44', 'TARGET_LOCALITY = "Torreón"',
                 'No existe una coincidencia exacta', '_DISCREPANCIAS.csv',
                 'el insertador no modifica H ni ninguna columna fuera de AK–AR',
                 'exclusivamente en AK–AR', 'La columna H y todas las columnas fuera de AK–AR permanecieron intactas'):
    if fragment not in insert_text:
        raise SystemExit(f'ERROR Insertador: falta {fragment}')
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
        'Actualizar datos','Configurar plantilla','Restaurar plantilla incluida','Buscar / abrir carpeta',
        'Equipo nuevo','Ciudad','Estado','sync_dependency_city_state','Vista previa de cédula',
        'Formato guardado','Precargar formato','ensure_initial_template_configuration')
require(PKG/'service_template_config.py', 'cell_map','sheet_name','Elegir plantilla propia','Guardar configuración')
require(PKG/'service_order_page.py','service_template_config.json','active_service_template.xlsx')

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
require(PKG/'main_window.py','closeEvent','self.database.backup(backups_dir())','Administración de formatos','Homologación DB')
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
