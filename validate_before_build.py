from __future__ import annotations

import ast
import csv
import io
import py_compile
import re
import shutil
import sqlite3
import tempfile
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parent

# 1. Every Python module must compile.
for path in sorted(root.rglob("*.py")):
    if ".venv" in path.parts or "build" in path.parts or "dist" in path.parts:
        continue
    py_compile.compile(str(path), doraise=True)

# 2. Protect the previously approved service-order workflow.
service_path = root / "codecafe_atlas" / "service_order_page.py"
tree = ast.parse(service_path.read_text(encoding="utf-8"))
cls = next(
    (node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "ServiceOrderPage"),
    None,
)
if cls is None:
    raise SystemExit("ERROR: no existe ServiceOrderPage")
methods = {node.name for node in cls.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
required = {
    "_load_last_output_folder", "_save_last_output_folder", "_default_output_folder",
    "choose_output_folder", "apply_reported_issue_template", "set_reported_issue_value",
    "field_values", "generate_document",
}
missing = sorted(required - methods)
if missing:
    raise SystemExit("ERROR: faltan funciones de Orden de Servicio: " + ", ".join(missing))

# 3. An included recovery template is optional. If present, validate it.
#    A user-supplied active template is a supported production configuration and
#    must not make the source/build depend on historical bundled filenames.
from codecafe_atlas.service_document_generator import validate_service_template
default_template = root / "modules" / "service_order" / "Plantilla predeterminada - Cédula de Servicio.xlsx"
if default_template.is_file():
    _found, missing, unknown = validate_service_template(default_template)
    if missing:
        raise SystemExit(f"ERROR: {default_template.name} no contiene: {sorted(missing)}")
    if unknown:
        raise SystemExit(f"ERROR: {default_template.name} contiene placeholders desconocidos: {sorted(unknown)}")
else:
    config_text = (root / "codecafe_atlas" / "service_template_config.py").read_text(encoding="utf-8")
    if "Cargar plantilla Excel propia" not in config_text or "No hay plantilla incluida disponible" not in config_text:
        raise SystemExit("ERROR: no hay plantilla de recuperación y el configurador no admite una plantilla propia independiente.")

# 4. Non-negotiable Directory requirements must remain in source.
directory_text = (root / "codecafe_atlas" / "directory_page.py").read_text(encoding="utf-8")
required_fragments = {
    "＋ Añadir edificio": "botón Añadir edificio",
    "class ClickableFrame": "encabezado de edificio clicable",
    "Editar edificio": "botón Editar edificio",
    "building_address": "dirección canónica bajo el edificio",
    "Equipos y contadores": "equipos y contadores por dependencia",
    "setChecked(False)": "sección colapsada por defecto",
    "latest_counter": "último contador por equipo",
}
for fragment, label in required_fragments.items():
    if fragment not in directory_text:
        raise SystemExit(f"ERROR Directorio: falta {label}.")

# 5. Public source must create a valid empty database on first run.
from codecafe_atlas.database import Database
_validation_root = tempfile.TemporaryDirectory(prefix="codecafe_atlas_validate_db_")
db_path = Path(_validation_root.name) / "atlas.db"
database = Database(db_path)
if not db_path.is_file():
    raise SystemExit("ERROR: Atlas no creó una base local vacía de prueba.")
connection = sqlite3.connect(db_path)
try:
    integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    if str(integrity).lower() != "ok":
        raise SystemExit(f"ERROR: integrity_check={integrity}")
    foreign_errors = list(connection.execute("PRAGMA foreign_key_check"))
    if foreign_errors:
        raise SystemExit(f"ERROR: relaciones rotas: {foreign_errors[:5]}")
    expected_tables = {"atlas_buildings","atlas_dependencies","atlas_equipment","atlas_counter_readings","atlas_service_orders","atlas_sync_records"}
    actual = {str(r[0]) for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    missing_tables = sorted(expected_tables - actual)
    if missing_tables:
        raise SystemExit(f"ERROR: faltan tablas canónicas: {missing_tables}")
finally:
    connection.close()
status = database.sync_identity_status()
if not status.get("installation_uuid"):
    raise SystemExit("ERROR Sync: falta installation_uuid.")

# 6. Public builds must create empty writable data/backups directories, not bundle operational DBs.
# Linux prepares them directly in build_linux.sh. Windows intentionally delegates
# release assembly to build_windows_release.py so it can build/smoke-test from a
# local non-synchronized path before copying the accepted distro back to source.
build_checks = (
    (root / "build_linux.sh", (root / "build_linux.sh",)),
    (root / "build_windows.bat", (root / "build_windows.bat", root / "build_windows_release.py")),
)
for build_entry, implementation_files in build_checks:
    texts = [path.read_text(encoding="utf-8").replace("\\", "/") for path in implementation_files]
    combined = "\n".join(texts)
    if "data" not in combined or "backups" not in combined:
        raise SystemExit(f"ERROR: {build_entry.name} no prepara data/backups.")
    if re.search(r"\.(?:db|sqlite|sqlite3)\b", combined, flags=re.IGNORECASE):
        raise SystemExit(f"ERROR: {build_entry.name} intenta empaquetar una base operacional.")

# The Windows entry point must actually delegate to the release builder whose
# data/backups preparation was validated above; otherwise a stale helper file
# could make this guard pass without being part of the real build.
windows_entry = (root / "build_windows.bat").read_text(encoding="utf-8")
if "build_windows_release.py" not in windows_entry:
    raise SystemExit("ERROR: build_windows.bat no invoca build_windows_release.py.")

# 7. Dashboard personalization must remain local and configurable.
home_text = (root / "codecafe_atlas" / "home_page.py").read_text(encoding="utf-8")
for fragment in ("Personalizar dashboard", "background_opacity", "background_mode", "Restaurar fondo predeterminado"):
    if fragment not in home_text:
        raise SystemExit(f"ERROR Dashboard: falta {fragment}")

# 8. The public source tree itself must not ship SQLite data files.
for candidate in root.rglob("*"):
    if candidate.is_file() and candidate.suffix.lower() in {".db", ".sqlite", ".sqlite3"}:
        raise SystemExit(f"ERROR Publicación: se encontró una base incluida: {candidate.relative_to(root)}")

# 9. Closing the main window must create one automatic, non-confirmed backup.
main_window_path = root / "codecafe_atlas" / "main_window.py"
main_tree = ast.parse(main_window_path.read_text(encoding="utf-8"))
main_class = next(
    (node for node in main_tree.body if isinstance(node, ast.ClassDef) and node.name == "MainWindow"),
    None,
)
if main_class is None:
    raise SystemExit("ERROR Cierre: no existe MainWindow.")
close_method = next(
    (node for node in main_class.body if isinstance(node, ast.FunctionDef) and node.name == "closeEvent"),
    None,
)
if close_method is None:
    raise SystemExit("ERROR Cierre: falta closeEvent con respaldo automático.")
close_source = ast.get_source_segment(main_window_path.read_text(encoding="utf-8"), close_method) or ""
for fragment in ("self.database.backup(backups_dir())", "self._close_backup_done", "event.accept()"):
    if fragment not in close_source:
        raise SystemExit(f"ERROR Cierre: falta {fragment}.")
if "QMessageBox.question" in close_source:
    raise SystemExit("ERROR Cierre: el respaldo automático no debe pedir confirmación.")
database_text = (root / "codecafe_atlas" / "database.py").read_text(encoding="utf-8")
for fragment in ("while destination.exists()", "sequence:02d"):
    if fragment not in database_text:
        raise SystemExit(f"ERROR Respaldo: falta protección contra colisiones ({fragment}).")

# 10. Service certificates must be grouped by the provider-report date, then category.
from codecafe_atlas.service_report_date import (
    date_folder_names,
    display_report_date,
    extract_provider_report_date,
    format_manual_report_date_input,
    month_folder_name,
    parse_manual_report_date,
    year_folder_name,
)

expected_date = "2026-07-30"
for sample, allow_unlabeled in (
    ("Fecha reporte del prestador de servicio: 30-07-2026", False),
    ("FECHA REPORTE DEL PRESTADOR DE SERVICIO\n30 / 07 / 2026", False),
    ("30 O7 2026", True),
):
    value, confidence = extract_provider_report_date(sample, allow_unlabeled=allow_unlabeled)
    if value != expected_date or confidence <= 0:
        raise SystemExit(f"ERROR Fecha de cédula: no se reconoció {sample!r}.")
if parse_manual_report_date("30-07-2026") != expected_date:
    raise SystemExit("ERROR Fecha de cédula: corrección manual no válida.")
if format_manual_report_date_input("09072026") != "09-07-2026":
    raise SystemExit("ERROR Fecha de cédula: no se insertaron guiones automáticamente.")
if format_manual_report_date_input("0907") != "09-07":
    raise SystemExit("ERROR Fecha de cédula: formato automático parcial incorrecto.")
if parse_manual_report_date("09072026") != "2026-07-09":
    raise SystemExit("ERROR Fecha de cédula: fecha compacta manual no válida.")
if parse_manual_report_date("31022026"):
    raise SystemExit("ERROR Fecha de cédula: se aceptó una fecha compacta imposible.")
if display_report_date(expected_date) != "30-07-2026":
    raise SystemExit("ERROR Fecha de cédula: formato visible incorrecto.")
if date_folder_names(expected_date) != ("2026", "Julio"):
    raise SystemExit("ERROR Fecha de cédula: jerarquía Año/Mes incorrecta.")
if year_folder_name(expected_date) != "2026":
    raise SystemExit("ERROR Fecha de cédula: carpeta anual incorrecta.")
if month_folder_name(expected_date) != "Julio":
    raise SystemExit("ERROR Fecha de cédula: carpeta mensual incorrecta.")
if date_folder_names("") != ("Año no identificado", "Mes no identificado"):
    raise SystemExit("ERROR Fecha de cédula: falta jerarquía para fechas no identificadas.")

pdf_text = (root / "codecafe_atlas" / "pdf_page.py").read_text(encoding="utf-8")

# 10a. DGTI/service folios must receive the required hyphen automatically.
pdf_tree = ast.parse(pdf_text)
formatter_functions = {
    node.name: node
    for node in pdf_tree.body
    if isinstance(node, ast.FunctionDef)
    and node.name in {
        "format_manual_service_identifier_input",
        "normalize_service_identifier",
    }
}
if set(formatter_functions) != {
    "format_manual_service_identifier_input",
    "normalize_service_identifier",
}:
    raise SystemExit("ERROR Folio DGTI: faltan las funciones de formato automático.")
formatter_module = ast.Module(
    body=[
        ast.Import(names=[ast.alias(name="re")]),
        formatter_functions["format_manual_service_identifier_input"],
        formatter_functions["normalize_service_identifier"],
    ],
    type_ignores=[],
)
ast.fix_missing_locations(formatter_module)
formatter_namespace: dict[str, object] = {}
exec(compile(formatter_module, str(root / "codecafe_atlas" / "pdf_page.py"), "exec"), formatter_namespace)
format_identifier = formatter_namespace["format_manual_service_identifier_input"]
normalize_identifier = formatter_namespace["normalize_service_identifier"]
for sample, expected in (
    ("R015422", "R-015422"),
    ("r015422", "R-015422"),
    ("R-015422", "R-015422"),
    ("REQ12345", "REQ-12345"),
    ("VENDOR-REQ101186", "VENDOR-REQ101186"),
):
    if format_identifier(sample) != expected:
        raise SystemExit(
            f"ERROR Folio DGTI: {sample!r} no produjo {expected!r}."
        )
if normalize_identifier("R 015422") != "R-015422":
    raise SystemExit("ERROR Folio DGTI: la normalización no insertó el guion.")

# 10b. The review panel must provide visual rotation and arrow-key field navigation.
review_class = next(
    (node for node in pdf_tree.body if isinstance(node, ast.ClassDef) and node.name == "ReviewDialog"),
    None,
)
if review_class is None:
    raise SystemExit("ERROR Revisión: no existe ReviewDialog.")
review_methods = {
    node.name
    for node in review_class.body
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
}
required_review_methods = {
    "display_pixmap",
    "rotate_clockwise",
    "visible_editable_fields",
    "focus_adjacent_field",
    "eventFilter",
}
missing_review_methods = sorted(required_review_methods - review_methods)
if missing_review_methods:
    raise SystemExit(
        "ERROR Revisión: faltan funciones de giro/navegación: "
        + ", ".join(missing_review_methods)
    )
for fragment in (
    'QPushButton("↻ Girar 90°")',
    "QTransform().rotate(self.rotation_degrees)",
    "Qt.Key.Key_Up",
    "Qt.Key.Key_Down",
    "field.installEventFilter(self)",
):
    if fragment not in pdf_text:
        raise SystemExit(f"ERROR Revisión: falta integración ({fragment}).")

for fragment in (
    "render_service_date_for_ocr",
    "Fecha reporte del prestador de servicio",
    "date_folder_names(result.report_date)",
    'archive_folder = f"{safe_year}/{safe_month}/{safe_category}"',
    "Año no identificado",
    "Mes no identificado",
    "class ReportDateLineEdit",
    "DD-MM-AAAA o DDMMAAAA",
    "class ServiceIdentifierLineEdit",
    "R-015422 o R015422",
    "format_manual_service_identifier_input",
):
    if fragment not in pdf_text:
        raise SystemExit(f"ERROR Separador mensual: falta {fragment}.")

# 11. ZIP export must never overwrite an existing file.
from codecafe_atlas.output_filename import next_available_path
with tempfile.TemporaryDirectory(prefix="codecafe_atlas_validate_zip_name_") as temp_dir:
    output_dir = Path(temp_dir)
    requested = output_dir / "Cedulas_por_mes_y_categoria.zip"
    if next_available_path(requested) != requested:
        raise SystemExit("ERROR ZIP: un nombre disponible fue modificado.")
    requested.write_bytes(b"original")
    second = output_dir / "Cedulas_por_mes_y_categoria_2.zip"
    if next_available_path(requested) != second:
        raise SystemExit("ERROR ZIP: no se propuso el sufijo _2.")
    second.write_bytes(b"second")
    third = output_dir / "Cedulas_por_mes_y_categoria_3.zip"
    if next_available_path(requested) != third:
        raise SystemExit("ERROR ZIP: no se incrementó hasta _3.")

for fragment in (
    "QFileDialog.Option.DontConfirmOverwrite",
    "next_available_path(destination)",
    'destination,\n                    "x",',
):
    if fragment not in pdf_text:
        raise SystemExit(f"ERROR ZIP: falta protección de autoincremento ({fragment}).")

identity_text = (root / "codecafe_atlas" / "identity.py").read_text(encoding="utf-8")
for fragment in ("CodeCafe Atlas", "io.codecafe.atlas", "CCA-JSS-2026", "Jaime Sánchez Sáenz"):
    if fragment not in identity_text:
        raise SystemExit(f"ERROR Identidad: falta {fragment}.")


# 12. The approved CodeCafe Atlas artwork must be bundled and used by the UI.
for asset_name in (
    "codecafe_atlas_logo.png",
    "codecafe_atlas_icon.png",
    "codecafe_atlas_icon.ico",
):
    asset = root / "assets" / asset_name
    if not asset.is_file() or asset.stat().st_size <= 0:
        raise SystemExit(f"ERROR Logo: falta {asset_name}.")

main_text = main_window_path.read_text(encoding="utf-8")
for fragment in (
    'asset_path("codecafe_atlas_icon.png")',
    'asset_path("codecafe_atlas_logo.png")',
    'def show_about(self):',
):
    if fragment not in main_text:
        raise SystemExit(f"ERROR Logo: falta integración en ventana principal ({fragment}).")
for fragment in (
    'navigation_panel.setObjectName("navigationPanel")',
    'navigation_logo.setObjectName("navigationLogo")',
    'asset_path("codecafe_atlas_logo.png")',
):
    if fragment not in main_text:
        raise SystemExit(f"ERROR Logo: falta integración en la navegación ({fragment}).")

# Build entry points may delegate the actual PyInstaller command to a helper.
# Validate the complete implementation chain instead of requiring every token
# to appear literally in the thin entry-point script.
logo_build_checks = (
    (root / "build_linux.sh", (root / "build_linux.sh",)),
    (root / "build_windows.bat", (root / "build_windows.bat", root / "build_windows_release.py")),
    (root / "build_macos.sh", (root / "build_macos.sh",)),
)
for build_entry, implementation_files in logo_build_checks:
    combined = "\n".join(
        path.read_text(encoding="utf-8").replace("\\", "/")
        for path in implementation_files
    )
    if "assets" not in combined or "codecafe_atlas" not in combined:
        raise SystemExit(f"ERROR Logo: {build_entry.name} no empaqueta los recursos gráficos.")


# 13. Every exported ZIP must include a UTF-8 CSV report at its root.
for fragment in (
    'report_rows: list[list[str | int]] = []',
    'EXPORT_REPORT_FILENAME',
    'build_export_report_csv(report_rows)',
):
    if fragment not in pdf_text:
        raise SystemExit(f"ERROR CSV: falta integración del reporte ({fragment}).")

from codecafe_atlas.export_report import (
    EXPORT_REPORT_FILENAME,
    EXPORT_REPORT_HEADERS,
    build_export_report_csv,
)
if EXPORT_REPORT_FILENAME != "reporte_exportacion.csv":
    raise SystemExit("ERROR CSV: nombre inesperado del reporte.")
if "Ruta PDF en ZIP" not in EXPORT_REPORT_HEADERS:
    raise SystemExit("ERROR CSV: falta la columna de ruta exportada.")

with tempfile.TemporaryDirectory(prefix="codecafe_atlas_validate_csv_") as temp_dir:
    archive_path = Path(temp_dir) / "resultado.zip"
    payload = build_export_report_csv([[
        "cedulas.pdf", 1, "R-015422", "Tóner", "09-07-2026",
        "OCR", 92, "2026/Julio/Tóner/R-015422.pdf",
    ]])
    with zipfile.ZipFile(archive_path, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(EXPORT_REPORT_FILENAME, payload)
    with zipfile.ZipFile(archive_path, "r") as archive:
        names = archive.namelist()
        if names != [EXPORT_REPORT_FILENAME]:
            raise SystemExit(f"ERROR CSV: contenido inesperado en prueba: {names}")
        stored = archive.read(EXPORT_REPORT_FILENAME)
        if not stored.startswith(b"\xef\xbb\xbf") or b"R-015422" not in stored:
            raise SystemExit("ERROR CSV: codificación o contenido inválido.")
        rows = list(csv.reader(io.StringIO(stored.decode("utf-8-sig"))))
        if rows[0] != list(EXPORT_REPORT_HEADERS) or rows[1][7] != "2026/Julio/Tóner/R-015422.pdf":
            raise SystemExit("ERROR CSV: columnas o datos inválidos.")



# 14. The intelligent separator must retain a local, non-document export history.
for fragment in (
    'QPushButton("Historial")',
    'class ExportHistoryDialog',
    'append_export_history({',
    'separator_history_path()',
    'La exportación quedó registrada en el historial local.',
):
    if fragment not in pdf_text:
        raise SystemExit(f"ERROR Historial: falta integración ({fragment}).")

from codecafe_atlas.separator_history import (
    append_export_history,
    clear_export_history,
    load_export_history,
)
with tempfile.TemporaryDirectory(prefix="codecafe_atlas_validate_history_") as temp_dir:
    history_path = Path(temp_dir) / "pdf_separator_history.json"
    first = append_export_history({
        "document_type": "Cédulas de servicio",
        "output_zip": str(Path(temp_dir) / "Cedulas.zip"),
        "source_files": [str(Path(temp_dir) / "cedulas.pdf")],
        "source_file_count": 1,
        "page_count": 3,
        "identified_count": 2,
        "provisional_count": 1,
        "categories": {"Tóner": 1, "Resto de fallas": 2},
        "report_file": "reporte_exportacion.csv",
    }, path=history_path)
    if not first.get("id") or not first.get("exported_at"):
        raise SystemExit("ERROR Historial: el registro no recibió identidad o fecha.")
    records = load_export_history(history_path)
    if len(records) != 1 or records[0].get("page_count") != 3:
        raise SystemExit("ERROR Historial: no se recuperó el registro guardado.")
    append_export_history({"page_count": 1}, path=history_path, limit=1)
    records = load_export_history(history_path)
    if len(records) != 1 or records[0].get("page_count") != 1:
        raise SystemExit("ERROR Historial: no se respetó el límite de retención.")
    clear_export_history(history_path)
    if load_export_history(history_path):
        raise SystemExit("ERROR Historial: no se eliminó el historial de prueba.")

# 15. Reusable service formats must be stored in SQLite and exposed by the UI.
formats_path = root / "codecafe_atlas" / "formats_page.py"
if not formats_path.is_file():
    raise SystemExit("ERROR Formatos: falta codecafe_atlas/formats_page.py")
formats_text = formats_path.read_text(encoding="utf-8")
for fragment in (
    "class FormatsPage",
    "formats_changed = Signal()",
    "format_requested = Signal(int)",
    "Guardar formato",
    "Usar en orden de servicio",
    "self.database.save_service_format",
):
    if fragment not in formats_text:
        raise SystemExit(f"ERROR Formatos: falta integración ({fragment}).")

main_text = main_window_path.read_text(encoding="utf-8")
for fragment in (
    "from .formats_page import FormatsPage",
    '("formats", "Administración de formatos", self.formats_page)',
    "self.formats_page.format_requested.connect",
):
    if fragment not in main_text:
        raise SystemExit(f"ERROR Formatos: falta navegación ({fragment}).")

service_text = service_path.read_text(encoding="utf-8")
# v1.0.24.25: the redundant saved-format preload bar was intentionally removed
# from Service Order. Template loading/configuration lives behind the dedicated
# "Cargar / configurar plantilla Excel" action. Backend saved-format support is
# retained for compatibility with Administración de formatos.
for forbidden in (
    'QLabel("Datos predefinidos")',
    'QPushButton("Precargar datos")',
    'self.template_label = QLabel(',
    'self.refresh_status = QLabel(',
    'Datos actualizados:',
):
    if forbidden in service_text:
        raise SystemExit(f"ERROR Servicio v1.0.24.25: elemento marcado para eliminación todavía visible ({forbidden}).")
for fragment in ("def apply_saved_format", "equipment_search_changed", 'QPushButton("Cargar / configurar plantilla Excel")'):
    if fragment not in service_text:
        raise SystemExit(f"ERROR Servicio v1.0.24.25: falta compatibilidad/sincronización ({fragment}).")
if "self.saved_format" in service_text:
    raise SystemExit("ERROR Servicio v1.0.24.25: quedó una dependencia del selector de formato eliminado.")

connection = sqlite3.connect(db_path)
try:
    formats_count = int(connection.execute(
        "SELECT COUNT(*) FROM service_formats"
    ).fetchone()[0])
    if formats_count != 0:
        raise SystemExit(
            f"ERROR Formatos: una base nueva debe iniciar vacía; contiene {formats_count}."
        )
finally:
    connection.close()

with tempfile.TemporaryDirectory(prefix="codecafe_atlas_validate_formats_") as temp_dir:
    test_path = Path(temp_dir) / "formats.db"
    shutil.copy2(db_path, test_path)
    test_db = Database(test_path)
    created_id = test_db.save_service_format({
        "name": "Formato de validación",
        "document_type": "Cédula de Servicio",
        "reported_issue": "Prueba",
        "active": True,
    })
    created = test_db.get_service_format(created_id)
    if created is None or created["reported_issue"] != "Prueba":
        raise SystemExit("ERROR Formatos: no se guardó el formato de prueba.")
    test_db.save_service_format({
        "name": "Formato de validación modificado",
        "document_type": "Dictaminación",
        "reported_issue": "Prueba modificada",
        "active": False,
    }, created_id)
    modified = test_db.get_service_format(created_id)
    if modified is None or modified["name"] != "Formato de validación modificado":
        raise SystemExit("ERROR Formatos: no se modificó el formato de prueba.")
    test_db.delete_service_format(created_id)
    if test_db.get_service_format(created_id) is not None:
        raise SystemExit("ERROR Formatos: no se eliminó el formato de prueba.")

# 16. The PDF module must use its new visible name without breaking internal compatibility.
pdf_library_text = (root / "codecafe_atlas" / "pdf_library_page.py").read_text(encoding="utf-8")
home_text = (root / "codecafe_atlas" / "home_page.py").read_text(encoding="utf-8")
main_text = main_window_path.read_text(encoding="utf-8")
for source_name, source_text, fragment in (
    ("pdf_library_page.py", pdf_library_text, '"Visor PDF"'),
    ("main_window.py", main_text, '("pdf_library", "Visor PDF", self.pdf_library_page)'),
    ("home_page.py", home_text, '("pdf_library", "Visor PDF"'),
):
    if fragment not in source_text:
        raise SystemExit(f"ERROR Visor PDF: falta el nombre nuevo en {source_name}.")
if "class PdfLibraryPage" not in pdf_library_text:
    raise SystemExit("ERROR Visor PDF: se rompió la clase interna PdfLibraryPage.")


# 17. Service folios must be unique only inside the current separator session.
pdf_page_path = root / "codecafe_atlas" / "pdf_page.py"
pdf_page_text = pdf_page_path.read_text(encoding="utf-8")
for fragment in (
    "def find_session_duplicate_identifier(",
    "def session_duplicate_row(",
    '"Folio duplicado en esta sesión"',
    'result.method = "Sin folio (duplicado)"',
    '"Folios duplicados en esta sesión"',
    "self.session_duplicate_rejections = 0",
):
    if fragment not in pdf_page_text:
        raise SystemExit(f"ERROR Folios únicos: falta integración ({fragment}).")

# Execute only the pure dataclass/normalization/helper nodes so the rule can be
# tested even on build hosts where PySide6 is not installed yet.
pdf_tree = ast.parse(pdf_page_text)
required_nodes = {
    "PageResult",
    "format_manual_service_identifier_input",
    "normalize_service_identifier",
    "find_session_duplicate_identifier",
}
selected_nodes = []
for node in pdf_tree.body:
    name = getattr(node, "name", None)
    if name in required_nodes:
        selected_nodes.append(node)
if {getattr(node, "name", None) for node in selected_nodes} != required_nodes:
    raise SystemExit("ERROR Folios únicos: no se pudieron aislar las funciones de validación.")
helper_module = ast.Module(body=selected_nodes, type_ignores=[])
ast.fix_missing_locations(helper_module)
helper_namespace = {"dataclass": __import__("dataclasses").dataclass, "re": __import__("re")}
exec(compile(helper_module, str(pdf_page_path), "exec"), helper_namespace)
PageResult = helper_namespace["PageResult"]
find_duplicate = helper_namespace["find_session_duplicate_identifier"]
make_result = lambda folio, deleted=False: PageResult(
    source_path="cedulas.pdf",
    source_name="cedulas.pdf",
    page_index=0,
    page_number=1,
    serial=folio,
    method="Manual",
    confidence=100,
    preview_text="",
    thumbnail_png=b"",
    deleted=deleted,
)
current_session = [make_result("R-015422"), make_result("REQ-12345")]
if find_duplicate(current_session, "r015422") != 0:
    raise SystemExit("ERROR Folios únicos: no detectó un folio repetido normalizado.")
if find_duplicate(current_session, "R015422", exclude_row=0) is not None:
    raise SystemExit("ERROR Folios únicos: la fila actual se comparó consigo misma.")
if find_duplicate([make_result("R-015422", deleted=True)], "R015422") is not None:
    raise SystemExit("ERROR Folios únicos: una entrada eliminada bloqueó el folio.")
if find_duplicate([], "R015422") is not None:
    raise SystemExit("ERROR Folios únicos: una sesión nueva heredó folios anteriores.")

# 18. Counter documents must use one editable identifier field for both the
# equipment serial and the logical PDF name. The same identifier must also be
# editable directly from the batch table. The extension is internal only.
counter_registry_html = (
    root / "modules" / "counter_registry" / "index.html"
).read_text(encoding="utf-8")
for pdf_asset in (
    root / "modules" / "counter_registry" / "vendor" / "pdfjs" / "pdf.js",
    root / "modules" / "counter_registry" / "vendor" / "pdfjs" / "pdf.worker.js",
    root / "modules" / "counter_registry" / "vendor" / "pdfjs" / "LICENSE",
    root / "modules" / "counter_registry" / "vendor" / "pdfjs" / "standard_fonts" / "LiberationSans-Regular.ttf",
):
    if not pdf_asset.is_file() or pdf_asset.stat().st_size == 0:
        raise SystemExit(f"ERROR Registro de contadores: falta recurso PDF local ({pdf_asset.name}).")
if "cdnjs.cloudflare.com/ajax/libs/pdf.js" in counter_registry_html:
    raise SystemExit("ERROR Registro de contadores: PDF.js sigue dependiendo de la red.")
for fragment in (
    "viewDocument.textContent = item.kind === 'pdf' ? 'Ver PDF' : 'Ver imagen'",
    "statusTools.className = 'status-review-tools'",
    'id="counterReviewSerial"',
    'function normalizeDocumentIdentifier(value)',
    'function renameQueueItemFromIdentifier(item, value)',
    'item.displayFileName = `${identifier}.pdf`',
    "item.equipment = identifier",
    "renameQueueItemFromIdentifier(item, identifier)",
    "function commitBatchSerialEdit(index, input)",
    "serialInput.className = 'batch-serial-input'",
    "serialInput.addEventListener('change'",
    "serialCell.appendChild(serialInput)",
    "$('equipmentId').value = identifier",
):
    if fragment not in counter_registry_html:
        raise SystemExit(
            f"ERROR Registro de contadores: falta el campo único serie/PDF ({fragment})."
        )
for forbidden_fragment in (
    'id="counterReviewFileName"',
    'Nombre del archivo',
    'function renameQueuedSource(',
    'function normalizeEditedDocumentName(',
    'candidate.file !== item.file',
):
    if forbidden_fragment in counter_registry_html:
        raise SystemExit(
            f"ERROR Registro de contadores: permanece el campo doble o propagación no autorizada ({forbidden_fragment})."
        )

# 18b. The enlarged counter review must preserve its keyboard-first workflow:
# Enter applies the current values and advances, while Up/Down move only among
# editable fields instead of changing numeric input values.
for fragment in (
    "const counterReviewEditableFieldIds = [",
    "function counterReviewEditableFields()",
    "function focusAdjacentCounterReviewField(currentField, direction)",
    "function handleCounterReviewKeyboard(event)",
    "event.key === 'ArrowUp' || event.key === 'ArrowDown'",
    "void applyCounterReviewAndNext();",
    "document.addEventListener('keydown', handleCounterReviewKeyboard);",
    "if (counterReview.navigating) return;",
):
    if fragment not in counter_registry_html:
        raise SystemExit(
            f"ERROR Registro de contadores: falta navegación por teclado ({fragment})."
        )


# 19. Counter insertion must use exact serial matches and audit discrepancies.
counter_inserter_path = root / "codecafe_atlas" / "counter_inserter_engine.py"
counter_inserter_text = counter_inserter_path.read_text(encoding="utf-8")

# Approximate serials may trigger a warning, but never become automatic matches.
counter_page_path = root / "codecafe_atlas" / "counter_inserter_page.py"
counter_page_tree = ast.parse(counter_page_path.read_text(encoding="utf-8"))
for forbidden in ("def levenshtein_distance(", "def unique_ocr_serial_match(", "listo_aproximado"):
    if forbidden in counter_inserter_text:
        raise SystemExit(f"ERROR Insertador exacto: permanece lógica aproximada ({forbidden}).")
for required_fragment in (
    "AUTHORIZED_WRITE_COLS = set(TARGET_COLS)",
    "No existe una coincidencia exacta",
    "def discrepancy_report_path(",
    "def write_discrepancy_report(",
    'return output_path.with_name(output_path.stem + "_DISCREPANCIAS.csv")',
    'def status_header_score(',
    'STATUS_VALUE = "En Operación"',
    'approximate_match=True',
):
    if required_fragment not in counter_inserter_text:
        raise SystemExit(f"ERROR Insertador exacto: falta protección ({required_fragment}).")
from codecafe_atlas.counter_inserter_engine import normalize_serial, parse_number
if normalize_serial(" ab-123 456 ") != "AB123456":
    raise SystemExit("ERROR Insertador exacto: normalización de serie inesperada.")
if parse_number("19.346") != 19346 or parse_number("19,346") != 19346:
    raise SystemExit("ERROR Insertador exacto: separadores de miles interpretados incorrectamente.")
if parse_number("23887.3") != 23887.3:
    raise SystemExit("ERROR Insertador exacto: contador equivalente decimal interpretado incorrectamente.")


# 20. PDF Viewer must detect exact duplicates and delete only with explicit control.
pdf_viewer_path = root / "codecafe_atlas" / "pdf_library_page.py"
pdf_viewer_text = pdf_viewer_path.read_text(encoding="utf-8")
for fragment in (
    'QPushButton("Detectar duplicados")',
    'QPushButton("Mostrar solo duplicados")',
    'QPushButton("Eliminar PDF…")',
    'find_exact_duplicate_groups(',
    '"Mover a la papelera"',
    '"Eliminar permanentemente"',
    'QFile.supportsMoveToTrash()',
    'trash_file.moveToTrash()',
    'path.unlink()',
    'path_is_within_root(path, self.root_folder)',
):
    if fragment not in pdf_viewer_text:
        raise SystemExit(f"ERROR Visor PDF: falta control de duplicados/eliminación ({fragment}).")

from codecafe_atlas.pdf_duplicate_tools import find_exact_duplicate_groups, path_is_within_root
with tempfile.TemporaryDirectory(prefix="codecafe_atlas_pdf_duplicates_") as temp_dir:
    test_root = Path(temp_dir)
    first = test_root / "primero.pdf"
    second = test_root / "copia_con_otro_nombre.pdf"
    same_size_different = test_root / "contenido_distinto.pdf"
    unique = test_root / "unico.pdf"
    first.write_bytes(b"PDF-DUPLICADO-123")
    second.write_bytes(b"PDF-DUPLICADO-123")
    same_size_different.write_bytes(b"PDF-OTRO-CONT-123")
    unique.write_bytes(b"UNICO")
    groups, errors = find_exact_duplicate_groups(
        [first, second, same_size_different, unique]
    )
    if errors:
        raise SystemExit(f"ERROR Visor PDF: análisis de prueba produjo errores: {errors}")
    normalized_groups = {frozenset(group) for group in groups}
    if normalized_groups != {frozenset((first, second))}:
        raise SystemExit(f"ERROR Visor PDF: grupos duplicados incorrectos: {groups}")
    if not path_is_within_root(first, test_root):
        raise SystemExit("ERROR Visor PDF: rechazó un PDF dentro de la carpeta seleccionada.")
    outside = test_root.parent / "fuera_de_la_carpeta.pdf"
    if path_is_within_root(outside, test_root):
        raise SystemExit("ERROR Visor PDF: permitió eliminar fuera de la carpeta seleccionada.")

print("Validación v1.0.19 correcta: Ciudad y Estado editables y sincronizados con el Directorio; funciones anteriores, identidad, módulos y base protegidos.")

# 15. The DB homologator must operate on the canonical clean schema, not legacy views.
sync_engine_text = (root / "codecafe_atlas" / "sync_engine.py").read_text(encoding="utf-8")
for fragment in (
    '"buildings": "atlas_buildings"',
    '"dependencies": "atlas_dependencies"',
    '"equipment": "atlas_equipment"',
    '"counter_records": "atlas_counter_readings"',
    '"service_orders": "atlas_service_orders"',
    '"people": "atlas_people"',
    '"offices": "atlas_offices"',
    'PRAGMA foreign_key_check',
    'atlas_pre_homologacion_',
):
    if fragment not in sync_engine_text:
        raise SystemExit(f"ERROR Homologación: falta protección/capacidad {fragment}.")
if '"locations"' in sync_engine_text.split('SYNC_TABLES =', 1)[1].split(')', 1)[0]:
    raise SystemExit("ERROR Homologación: locations no debe ser una entidad canónica independiente.")
sync_page_text = (root / "codecafe_atlas" / "sync_compare_page.py").read_text(encoding="utf-8")
if "Mantener ambos" in sync_page_text:
    raise SystemExit("ERROR Homologación: no debe permitirse crear duplicados con 'Mantener ambos'.")

# 18. Full cumulative recovery guard for all verified historical workflows.
import runpy
runpy.run_path(str(root / "validate_full_functionality.py"), run_name="__atlas_full_function_validation__")

# Counter shared-history regression: both counter interfaces must write/update
# the canonical atlas_counter_readings table, never UPSERT the compatibility view.
_counter_validation_root = tempfile.TemporaryDirectory(prefix="codecafe_atlas_validate_counter_")
_counter_db = Database(Path(_counter_validation_root.name) / "atlas.db")
_counter_building = _counter_db.save_building({"name": "Counter Validation Building"})
_counter_dependency = _counter_db.save_dependency({"name": "Counter Validation Dependency", "building_id": _counter_building})
_counter_equipment = _counter_db.save_equipment({
    "dependency_id": _counter_dependency, "equipment_type": "Printer", "brand": "HP",
    "model": "Validation", "serial_number": "ATLASCOUNTERTEST001", "inventory_number": "",
    "assigned_user": "", "ip_address": "", "hostname": "", "status": "Activo", "notes": "",
})
_counter_uid = _counter_db.save_equipment_counter(_counter_equipment, {
    "reading_date": "2026-08-17", "total_prints": 100, "letter_prints": 90,
})
_counter_db.save_equipment_counter(_counter_equipment, {
    "reading_date": "2026-08-17", "total_prints": 101, "letter_prints": 91,
}, _counter_uid)
_counter_result = _counter_db.save_counter_records([{
    "id": _counter_uid, "equipment": "ATLASCOUNTERTEST001", "date": "2026-08-17",
    "total": 102, "equivalent": 92, "format": "validation",
}])
_counter_rows = _counter_db.list_equipment_counter_records(_counter_equipment)
if len(_counter_rows) != 1 or float(_counter_rows[0]["total_prints"]) != 102:
    raise SystemExit("ERROR Contadores: Registro de contadores y Contador de impresiones no comparten correctamente el historial canónico.")
_counter_db_path = Path(_counter_validation_root.name) / "atlas.db"
_counter_connection = sqlite3.connect(_counter_db_path)
try:
    _canonical_count = _counter_connection.execute("SELECT COUNT(*) FROM atlas_counter_readings").fetchone()[0]
    if _canonical_count != 1:
        raise SystemExit("ERROR Contadores: la escritura no quedó exclusivamente en atlas_counter_readings.")
finally:
    _counter_connection.close()
_counter_validation_root.cleanup()
print("COUNTER SHARED HISTORY VALIDATION: PASS")

# Counter-discovered equipment registration: one dependency selection must
# create each normalized serial once and attach both new and earlier readings.
_registration_root = tempfile.TemporaryDirectory(prefix="codecafe_atlas_validate_counter_registration_")
_registration_db_path = Path(_registration_root.name) / "atlas.db"
_registration_db = Database(_registration_db_path)
_registration_building = _registration_db.save_building({"name": "Bulk Registration Building"})
_registration_dependency = _registration_db.save_dependency({
    "name": "Bulk Registration Dependency",
    "building_id": _registration_building,
})
_registered_incomplete = _registration_db.save_equipment({
    "dependency_id": _registration_dependency,
    "equipment_type": "Impresora",
    "brand": "HP",
    "model": "HP Existing Validation",
    "serial_number": "REGISTERED-003",
    "inventory_number": "",
    "assigned_user": "",
    "ip_address": "",
    "hostname": "",
    "status": "Activo",
    "notes": "",
})
_registration_db.save_counter_records([{
    "id": "orphan-reading-001",
    "equipment": "HP-NEW-001",
    "model": "HP LaserJet Validation",
    "date": "2026-08-28T08:00:00",
    "total": 100,
}])
_new_records = [
    {
        "id": "new-reading-001",
        "equipment": "HP NEW 001",
        "model": "HP LaserJet Validation",
        "hostname": "NPI000001",
        "date": "2026-08-28T09:00:00",
        "total": 110,
    },
    {
        "id": "new-reading-002",
        "equipment": "SHARP-NEW-002",
        "model": "Sharp MX Validation",
        "hostname": "NPI000002",
        "date": "2026-08-28T09:05:00",
        "total": 220,
    },
    {
        "id": "existing-reading-003",
        "equipment": "REGISTERED-003",
        "model": "HP Existing Validation",
        "hostname": "NPI000003",
        "date": "2026-08-28T09:10:00",
        "total": 330,
    },
]
_missing = _registration_db.missing_counter_equipment(_new_records)
if len(_missing) != 2:
    raise SystemExit(f"ERROR Alta masiva: se esperaban 2 series nuevas y se detectaron {len(_missing)}.")
_registration_result = _registration_db.save_counter_records(
    _new_records,
    register_missing=True,
    dependency_id=_registration_dependency,
)
if _registration_result.get("equipment_created") != 2:
    raise SystemExit(f"ERROR Alta masiva: creación inesperada {_registration_result}.")
if _registration_result.get("historical_linked") != 1:
    raise SystemExit(f"ERROR Alta masiva: no vinculó la lectura histórica huérfana {_registration_result}.")
if _registration_result.get("hostnames_completed") != 3:
    raise SystemExit(f"ERROR Hostname: no completó los tres campos vacíos {_registration_result}.")
if _registration_db.missing_counter_equipment(_new_records):
    raise SystemExit("ERROR Alta masiva: las series recién registradas siguen apareciendo como faltantes.")
_registration_connection = sqlite3.connect(_registration_db_path)
try:
    _registration_connection.row_factory = sqlite3.Row
    _created_rows = _registration_connection.execute(
        "SELECT id,dependency_id,brand,model,serial_number,hostname,status FROM atlas_equipment ORDER BY id"
    ).fetchall()
    if len(_created_rows) != 3:
        raise SystemExit(f"ERROR Alta masiva: existen {len(_created_rows)} equipos en vez de 3.")
    if {row["brand"] for row in _created_rows} != {"HP", "Sharp"}:
        raise SystemExit("ERROR Alta masiva: no conservó fabricantes explícitos de los modelos OCR.")
    if any(int(row["dependency_id"]) != _registration_dependency for row in _created_rows):
        raise SystemExit("ERROR Alta masiva: algún equipo quedó fuera de la dependencia elegida.")
    _hostnames = {row["serial_number"]: row["hostname"] for row in _created_rows}
    if _hostnames != {
        "REGISTERED-003": "NPI000003",
        "HP NEW 001": "NPI000001",
        "SHARP-NEW-002": "NPI000002",
    }:
        raise SystemExit(f"ERROR Hostname: valores guardados inesperados {_hostnames}.")
    _unlinked = _registration_connection.execute(
        "SELECT COUNT(*) FROM atlas_counter_readings WHERE equipment_id IS NULL"
    ).fetchone()[0]
    if _unlinked != 0:
        raise SystemExit(f"ERROR Alta masiva: quedaron {_unlinked} lecturas sin vincular.")
finally:
    _registration_connection.close()

_preserved_result = _registration_db.save_counter_records([{
    "id": "preserve-hostname-reading",
    "equipment": "REGISTERED-003",
    "model": "HP Existing Validation",
    "hostname": "DIFFERENT-HOST",
    "date": "2026-08-28T09:20:00",
    "total": 340,
}])
if _preserved_result.get("hostnames_preserved") != 1:
    raise SystemExit(f"ERROR Hostname: no protegió el hostname existente {_preserved_result}.")
_conflict_owner = _registration_db.save_equipment({
    "dependency_id": _registration_dependency,
    "equipment_type": "Impresora",
    "brand": "HP",
    "model": "HP Conflict Owner",
    "serial_number": "HOST-OWNER-004",
    "inventory_number": "",
    "assigned_user": "",
    "ip_address": "",
    "hostname": "NPI-CONFLICT",
    "status": "Activo",
    "notes": "",
})
_conflict_target = _registration_db.save_equipment({
    "dependency_id": _registration_dependency,
    "equipment_type": "Impresora",
    "brand": "HP",
    "model": "HP Conflict Target",
    "serial_number": "HOST-TARGET-005",
    "inventory_number": "",
    "assigned_user": "",
    "ip_address": "",
    "hostname": "",
    "status": "Activo",
    "notes": "",
})
_conflict_result = _registration_db.save_counter_records([{
    "id": "conflict-hostname-reading",
    "equipment": "HOST-TARGET-005",
    "model": "HP Conflict Target",
    "hostname": "NPI-CONFLICT",
    "date": "2026-08-28T09:30:00",
    "total": 500,
}])
if len(_conflict_result.get("hostname_conflicts") or []) != 1:
    raise SystemExit(f"ERROR Hostname: no detectó el hostname duplicado {_conflict_result}.")
_registration_connection = sqlite3.connect(_registration_db_path)
try:
    _preserved_hostname = _registration_connection.execute(
        "SELECT hostname FROM atlas_equipment WHERE id=?", (_registered_incomplete,)
    ).fetchone()[0]
    _target_hostname = _registration_connection.execute(
        "SELECT hostname FROM atlas_equipment WHERE id=?", (_conflict_target,)
    ).fetchone()[0]
    if _preserved_hostname != "NPI000003" or _target_hostname != "":
        raise SystemExit("ERROR Hostname: Atlas sobrescribió o duplicó un hostname protegido.")
finally:
    _registration_connection.close()

try:
    _registration_db.save_counter_records(
        [{
            "id": "invalid-dependency-reading",
            "equipment": "INVALID-DEPENDENCY-003",
            "model": "HP Validation",
            "date": "2026-08-28T10:00:00",
            "total": 300,
        }],
        register_missing=True,
        dependency_id=999999999,
    )
except ValueError:
    pass
else:
    raise SystemExit("ERROR Alta masiva: aceptó una dependencia inexistente.")
_registration_connection = sqlite3.connect(_registration_db_path)
try:
    _invalid_equipment = _registration_connection.execute(
        "SELECT COUNT(*) FROM atlas_equipment WHERE serial_number='INVALID-DEPENDENCY-003'"
    ).fetchone()[0]
    _invalid_reading = _registration_connection.execute(
        "SELECT COUNT(*) FROM atlas_counter_readings WHERE external_uid='invalid-dependency-reading'"
    ).fetchone()[0]
    if _invalid_equipment or _invalid_reading:
        raise SystemExit("ERROR Alta masiva: una operación inválida dejó datos parciales.")
finally:
    _registration_connection.close()

_typo_reading = {
    "id": "counter-serial-typo-validation",
    "equipment": "REGISTEERD-003",
    "model": "HP Existing Validation",
    "file": "REGISTEERD-003.pdf",
    "date": "2026-08-28T09:40:00",
    "total": 700,
    "equivalent": 650,
    "duplex": 300,
    "jams": 1,
    "misfeeds": 0,
    "economode": 0,
    "format": "hp_configuration",
}
_registration_db.save_counter_records([_typo_reading])
_typo_suggestions = _registration_db.counter_serial_suggestions("REGISTEERD-003")
if not _typo_suggestions or _typo_suggestions[0]["serial_number"] != "REGISTERED-003":
    raise SystemExit(f"ERROR Historial: no advirtió la serie parecida {_typo_suggestions}.")
_typo_reading["serial_number"] = "REGISTERED-003"
_typo_result = _registration_db.update_counter_record(
    "counter-serial-typo-validation", _typo_reading
)
if not _typo_result.get("linked_to_inventory"):
    raise SystemExit(f"ERROR Historial: la corrección no vinculó el equipo {_typo_result}.")
_registration_connection = sqlite3.connect(_registration_db_path)
try:
    _registration_connection.row_factory = sqlite3.Row
    _corrected = _registration_connection.execute(
        "SELECT equipment_id,serial_snapshot FROM atlas_counter_readings WHERE external_uid=?",
        ("counter-serial-typo-validation",),
    ).fetchone()
    _audit_count = _registration_connection.execute(
        "SELECT COUNT(*) FROM atlas_counter_reading_edits WHERE record_uid=?",
        ("counter-serial-typo-validation",),
    ).fetchone()[0]
    if (
        _corrected is None
        or int(_corrected["equipment_id"]) != _registered_incomplete
        or _corrected["serial_snapshot"] != "REGISTERED-003"
        or _audit_count != 1
    ):
        raise SystemExit("ERROR Historial: corrección o trazabilidad incompleta.")
finally:
    _registration_connection.close()
_registration_root.cleanup()
print("COUNTER BULK EQUIPMENT REGISTRATION VALIDATION: PASS")
