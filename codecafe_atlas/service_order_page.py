from __future__ import annotations

import html
import json
import shutil
from pathlib import Path

from PySide6.QtCore import QDate, QTime, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from .database import Database
from .paths import data_dir, module_dir
from .service_document_generator import (
    SERVICE_REQUIRED_PLACEHOLDERS,
    SERVICE_SUPPORTED_PLACEHOLDERS,
    generate_service_document,
    validate_service_template,
)
from .ui_helpers import line_edit, notes_edit, page_header


def read_only_line(placeholder: str = "") -> QLineEdit:
    widget = line_edit(placeholder)
    widget.setReadOnly(True)
    widget.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    return widget


def address_text(row) -> str:
    if row is None:
        return ""
    street_number = " ".join(
        part for part in [str(row["street"] or "").strip(), str(row["exterior_number"] or "").strip()]
        if part
    )
    parts = [street_number]
    if str(row["colony"] or "").strip():
        parts.append(f'Col. {str(row["colony"]).strip()}')
    if str(row["postal_code"] or "").strip():
        parts.append(f'C.P. {str(row["postal_code"]).strip()}')
    return ", ".join(part for part in parts if part)


def city_state_text(row) -> str:
    if row is None:
        return ""
    return " / ".join(
        part for part in [str(row["city"] or "").strip(), str(row["state"] or "").strip()]
        if part
    )


REPORTED_ISSUE_TEMPLATES = {
    "Entrada manual": "",
    "Tóner": (
        "Se acude a sitio, se saca una hoja de estado de consumibles para "
        "verificar los niveles de tóner, se valida que hace falta un tóner "
        "nuevo, se cambia, se valida con el usuario que pueda imprimir "
        "correctamente y se firma conformidad."
    ),
    "Vincular impresora": (
        "Se acude a sitio y se verifica que el usuario no pueda mandar a "
        "imprimir. Se detecta que el usuario cambió de sistema operativo y "
        "no tiene la impresora instalada. Se instala la impresora y se "
        "verifica que el usuario pueda mandar a imprimir correctamente."
    ),
    "Escáner Ricoh": (
        "Se acude a sitio y se valida el error reportado por el usuario. "
        "La IP de la PC del usuario cambió y ya no tiene conexión con la "
        "impresora. Se ingresa al Command Center de la impresora y se agrega "
        "la nueva IP asignada a la PC. El usuario realiza una prueba y puede "
        "escanear correctamente."
    ),
}

class ServiceOrderPage(QWidget):
    def __init__(self, database: Database):
        super().__init__()
        self.database = database
        self.current_id: int | None = None
        self.current_output_path = ""
        self.all_dependency_rows = []
        self.all_equipment_rows = []
        self.dependency_rows = {}
        self.equipment_rows = {}
        self.order_rows = {}
        self._last_dependency_id: int | None = None
        self.folder = module_dir("service_order")
        self.template_path = self.folder / "Formato de referencia - Cédulas.xlsx"
        self.service_template_path = self.folder / "Formato de referencia - Cédula de Servicio.xlsx"
        self.default_service_template_path = self.folder / "Plantilla predeterminada - Cédula de Servicio.xlsx"
        self.settings_path = data_dir() / "service_order_settings.json"
        self.last_output_folder = self._load_last_output_folder()

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 18)
        root.addWidget(page_header(
            "Generador de orden de servicio / cédula",
            "Selecciona primero la dependencia. Puedes usar un equipo registrado o capturar uno nuevo; la dirección y el CTA se cargan automáticamente."
        ))

        template_bar = QHBoxLayout()
        reload_button = QPushButton("Actualizar datos")
        replace_button = QPushButton("Reemplazar plantilla")
        validate_button = QPushButton("Validar plantilla")
        restore_button = QPushButton("Restaurar plantilla incluida")
        open_template_folder = QPushButton("Buscar / abrir carpeta")
        self.template_label = QLabel(str(self.service_template_path))
        self.template_label.setWordWrap(True)
        template_bar.addWidget(reload_button)
        template_bar.addWidget(replace_button)
        template_bar.addWidget(validate_button)
        template_bar.addWidget(restore_button)
        template_bar.addWidget(open_template_folder)
        template_bar.addWidget(self.template_label, 1)
        root.addLayout(template_bar)

        saved_format_bar = QHBoxLayout()
        saved_format_bar.addWidget(QLabel("Formato guardado"))
        self.saved_format = QComboBox()
        self.saved_format.setMinimumContentsLength(30)
        self.saved_format.setToolTip(
            "Selecciona un formato administrado en el módulo Administración de formatos."
        )
        apply_saved_format_button = QPushButton("Precargar formato")
        apply_saved_format_button.setObjectName("secondaryButton")
        saved_format_bar.addWidget(self.saved_format, 1)
        saved_format_bar.addWidget(apply_saved_format_button)
        root.addLayout(saved_format_bar)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter, 1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        form_host = QWidget()
        form_root = QVBoxLayout(form_host)
        form_root.setContentsMargins(5, 5, 14, 5)

        # Document data
        doc_box = QGroupBox("Documento")
        doc_form = QFormLayout(doc_box)
        self.document_type = QComboBox()
        self.document_type.addItems([
            "Cédula de Servicio",
            "Mantenimiento Preventivo",
            "Dictaminación",
        ])
        self.folio = line_edit("Folio completamente editable")
        self.dgti_report = line_edit("Reporte asignado por DGTI")
        self.provider_report = line_edit("Ejemplo: REP-0001")
        self.report_date = QDateEdit()
        self.report_date.setCalendarPopup(True)
        self.report_date.setDisplayFormat("dd/MM/yyyy")
        self.report_date.setDate(QDate.currentDate())
        self.report_time = QTimeEdit()
        self.report_time.setDisplayFormat("HH:mm")
        self.report_time.setTime(QTime.currentTime())
        self.output_folder = line_edit("Seleccione dónde guardar las cédulas")
        if self.last_output_folder:
            self.output_folder.setText(self.last_output_folder)
        browse_output = QPushButton("Examinar…")
        output_row = QWidget()
        output_layout = QHBoxLayout(output_row)
        output_layout.setContentsMargins(0, 0, 0, 0)
        output_layout.addWidget(self.output_folder, 1)
        output_layout.addWidget(browse_output)

        doc_form.addRow("Tipo de documento", self.document_type)
        doc_form.addRow("Folio *", self.folio)
        doc_form.addRow("Reporte DGTI", self.dgti_report)
        doc_form.addRow("Reporte del prestador", self.provider_report)
        doc_form.addRow("Fecha", self.report_date)
        doc_form.addRow("Hora", self.report_time)
        doc_form.addRow("Guardar en *", output_row)

        # Dependency selection and automatic data
        dependency_box = QGroupBox("Dependencia y datos automáticos")
        dependency_form = QFormLayout(dependency_box)
        self.dependency_filter = line_edit("Buscar dependencia, edificio, piso, juzgado o CTA")
        self.dependency = QComboBox()
        self.dependency.setEditable(False)
        self.dependency.setMinimumContentsLength(38)
        self.dependency_status = QLabel("")
        self.dependency_status.setObjectName("pageSubtitle")

        self.auto_dependency_name = read_only_line()
        self.auto_building = read_only_line()
        self.auto_floor = read_only_line()
        self.auto_office = read_only_line()
        self.auto_address = read_only_line()
        self.auto_city = line_edit("Ciudad")
        self.auto_state = line_edit("Estado")
        self.auto_cta = read_only_line()
        self.auto_phone = read_only_line()
        self.auto_email = read_only_line()

        dependency_form.addRow("Buscar", self.dependency_filter)
        dependency_form.addRow("Dependencia *", self.dependency)
        dependency_form.addRow("Disponibles", self.dependency_status)
        dependency_form.addRow("Dependencia seleccionada", self.auto_dependency_name)
        dependency_form.addRow("Edificio", self.auto_building)
        dependency_form.addRow("Piso", self.auto_floor)
        dependency_form.addRow("Oficina", self.auto_office)
        dependency_form.addRow("Dirección", self.auto_address)
        dependency_form.addRow("Ciudad", self.auto_city)
        dependency_form.addRow("Estado", self.auto_state)
        dependency_form.addRow("CTA registrado", self.auto_cta)
        dependency_form.addRow("Teléfono", self.auto_phone)
        dependency_form.addRow("Correo", self.auto_email)

        # Equipment filtered by selected dependency, with optional manual capture.
        equipment_box = QGroupBox("Equipo")
        equipment_form = QFormLayout(equipment_box)
        self.manual_equipment = QCheckBox(
            "Equipo nuevo: capturar manualmente y agregarlo al inventario"
        )
        self.equipment_filter = line_edit("Buscar por serie, inventario, marca, modelo, IP o hostname")
        self.equipment = QComboBox()
        self.equipment.setEditable(False)
        self.equipment.setMinimumContentsLength(38)
        self.equipment_status = QLabel("")
        self.equipment_status.setObjectName("pageSubtitle")

        self.auto_equipment_type = line_edit("Impresora, escáner, multifuncional…")
        self.auto_brand = line_edit("Marca")
        self.auto_model = line_edit("Modelo")
        self.auto_serial = line_edit("Número de serie")
        self.auto_inventory_number = line_edit("Número de inventario institucional")
        self.auto_ip = line_edit("IP, si está disponible")
        self.auto_hostname = line_edit("Hostname, si está disponible")
        self.manual_equipment_status = QComboBox()
        self.manual_equipment_status.addItems([
            "Activo", "En reparación", "Fuera de servicio", "Retirado", "Desconocido"
        ])
        self.manual_equipment_status.setEnabled(False)
        for widget in self._equipment_detail_widgets():
            widget.setReadOnly(True)

        equipment_form.addRow("Modo", self.manual_equipment)
        equipment_form.addRow("Buscar", self.equipment_filter)
        equipment_form.addRow("Equipo registrado", self.equipment)
        equipment_form.addRow("Disponibles", self.equipment_status)
        equipment_form.addRow("Tipo *", self.auto_equipment_type)
        equipment_form.addRow("Marca", self.auto_brand)
        equipment_form.addRow("Modelo", self.auto_model)
        equipment_form.addRow("Número de serie", self.auto_serial)
        equipment_form.addRow("No. de inventario", self.auto_inventory_number)
        equipment_form.addRow("IP", self.auto_ip)
        equipment_form.addRow("Hostname", self.auto_hostname)
        equipment_form.addRow("Estado al registrar", self.manual_equipment_status)

        # Editable people/validation fields, prefilled from dependency CTA
        validation_box = QGroupBox("Responsable y validación")
        validation_form = QFormLayout(validation_box)
        self.responsible_name = line_edit("Se carga inicialmente con el CTA de la dependencia")
        self.validator_name = line_edit("Servidor público que valida")
        self.validator_role = line_edit("Cargo")
        self.validator_phone = line_edit("Teléfono")
        self.movement_type = QComboBox()
        self.movement_type.addItems([
            "", "Sustitución", "Actualización", "Reubicación",
            "Incremento", "Disminución"
        ])
        validation_form.addRow("Responsable del equipo", self.responsible_name)
        validation_form.addRow("Servidor público que valida", self.validator_name)
        validation_form.addRow("Cargo", self.validator_role)
        validation_form.addRow("Teléfono", self.validator_phone)
        validation_form.addRow("Movimiento", self.movement_type)

        # Service information
        service_box = QGroupBox("Servicio")
        service_form = QFormLayout(service_box)
        self.reported_issue_template = QComboBox()
        self.reported_issue_template.addItems(
            list(REPORTED_ISSUE_TEMPLATES.keys())
        )
        self.reported_issue_template.setToolTip(
            "Selecciona una plantilla o utiliza Entrada manual."
        )

        self.reported_issue = notes_edit(
            "Selecciona una plantilla o escribe manualmente la falla reportada"
        )
        self.reported_issue.setMinimumHeight(125)
        self.reported_issue.setMaximumHeight(220)

        reported_issue_host = QWidget()
        reported_issue_layout = QVBoxLayout(reported_issue_host)
        reported_issue_layout.setContentsMargins(0, 0, 0, 0)
        reported_issue_layout.setSpacing(7)
        reported_issue_layout.addWidget(self.reported_issue_template)
        reported_issue_layout.addWidget(self.reported_issue)

        self.diagnosis = notes_edit("Diagnóstico")
        self.solution = notes_edit("Solución o servicio realizado")
        self.service_notes = notes_edit("Observaciones")

        self.diagnosis_date = QDateEdit()
        self.diagnosis_date.setCalendarPopup(True)
        self.diagnosis_date.setDisplayFormat("dd/MM/yyyy")
        self.diagnosis_date.setDate(QDate.currentDate())
        self.diagnosis_time = QTimeEdit()
        self.diagnosis_time.setDisplayFormat("HH:mm")
        self.diagnosis_time.setTime(QTime.currentTime())
        self.solution_date = QDateEdit()
        self.solution_date.setCalendarPopup(True)
        self.solution_date.setDisplayFormat("dd/MM/yyyy")
        self.solution_date.setDate(QDate.currentDate())
        self.solution_time = QTimeEdit()
        self.solution_time.setDisplayFormat("HH:mm")
        self.solution_time.setTime(QTime.currentTime())

        self.technician_name = line_edit("Nombre del técnico del prestador")
        self.equipment_operates = QComboBox()
        self.equipment_operates.addItems(["Sí", "No", "No aplica"])
        self.equipment_condition = QComboBox()
        self.equipment_condition.addItems(["No", "Sí", "No aplica"])
        service_form.addRow(
            "Falla reportada",
            reported_issue_host,
        )
        service_form.addRow("Diagnóstico", self.diagnosis)
        service_form.addRow("Fecha de diagnóstico", self.diagnosis_date)
        service_form.addRow("Hora de diagnóstico", self.diagnosis_time)
        service_form.addRow("Solución / servicio", self.solution)
        service_form.addRow("Fecha de solución", self.solution_date)
        service_form.addRow("Hora de solución", self.solution_time)
        service_form.addRow("Observaciones", self.service_notes)
        service_form.addRow("Técnico", self.technician_name)
        service_form.addRow("¿Opera adecuadamente?", self.equipment_operates)
        service_form.addRow("¿Rayaduras o golpes?", self.equipment_condition)

        actions = QHBoxLayout()
        new_button = QPushButton("Nuevo / limpiar")
        save_button = QPushButton("Guardar registro")
        save_button.setObjectName("primaryButton")
        preview_button = QPushButton("Vista previa de cédula")
        generate_button = QPushButton("Guardar y generar cédula")
        generate_button.setObjectName("primaryButton")
        delete_button = QPushButton("Eliminar registro")
        delete_button.setObjectName("dangerButton")
        actions.addWidget(new_button)
        actions.addStretch(1)
        actions.addWidget(delete_button)
        actions.addWidget(save_button)
        actions.addWidget(preview_button)
        actions.addWidget(generate_button)

        form_root.addWidget(doc_box)
        form_root.addWidget(dependency_box)
        form_root.addWidget(equipment_box)
        form_root.addWidget(validation_box)
        form_root.addWidget(service_box)
        form_root.addLayout(actions)
        form_root.addStretch(1)
        scroll.setWidget(form_host)
        splitter.addWidget(scroll)

        # History
        history_host = QWidget()
        history_layout = QVBoxLayout(history_host)
        history_layout.setContentsMargins(12, 5, 5, 5)
        search_row = QHBoxLayout()
        self.search = line_edit("Buscar folio, serie, modelo o dependencia")
        search_row.addWidget(self.search, 1)
        history_layout.addLayout(search_row)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels([
            "Fecha", "Folio", "Tipo", "Serie", "Modelo", "Dependencia", "Archivo"
        ])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        history_layout.addWidget(self.table, 1)
        open_file_button = QPushButton("Abrir archivo seleccionado")
        history_layout.addWidget(open_file_button)
        splitter.addWidget(history_host)
        splitter.setSizes([790, 590])

        reload_button.clicked.connect(self.full_refresh)
        replace_button.clicked.connect(self.replace_template)
        validate_button.clicked.connect(self.validate_template)
        restore_button.clicked.connect(self.restore_default_template)
        open_template_folder.clicked.connect(self.open_module_folder)
        browse_output.clicked.connect(self.choose_output_folder)
        self.dependency_filter.textChanged.connect(self.refresh_dependencies)
        self.dependency.currentIndexChanged.connect(self.dependency_changed)
        self.equipment_filter.textChanged.connect(self.refresh_equipment)
        self.equipment.currentIndexChanged.connect(self.fill_equipment_details)
        self.manual_equipment.toggled.connect(self.equipment_mode_changed)
        self.search.textChanged.connect(self.refresh_history)
        self.table.itemSelectionChanged.connect(self.load_selected_order)
        new_button.clicked.connect(self.clear_form)
        save_button.clicked.connect(self.save_record)
        preview_button.clicked.connect(self.show_document_preview)
        generate_button.clicked.connect(self.generate_document)
        delete_button.clicked.connect(self.delete_record)
        open_file_button.clicked.connect(self.open_selected_file)
        self.document_type.currentTextChanged.connect(self.update_document_fields)
        self.reported_issue_template.currentTextChanged.connect(
            self.apply_reported_issue_template
        )
        apply_saved_format_button.clicked.connect(
            self.apply_selected_saved_format
        )

        self.full_refresh()
        self.update_document_fields()

    def refresh_saved_formats(self, preserve_id: int | None = None) -> None:
        if preserve_id is None:
            preserve_id = self.saved_format.currentData()
        rows = self.database.list_service_formats(active_only=True)
        self.saved_format.blockSignals(True)
        self.saved_format.clear()
        self.saved_format.addItem("Seleccionar formato…", None)
        for row in rows:
            description = str(row["description"] or "").strip()
            label = str(row["name"] or "")
            if description:
                label = f"{label} — {description}"
            self.saved_format.addItem(label, int(row["id"]))
        index = self.saved_format.findData(preserve_id)
        self.saved_format.setCurrentIndex(index if index >= 0 else 0)
        self.saved_format.blockSignals(False)

    def apply_selected_saved_format(self) -> None:
        format_id = self.saved_format.currentData()
        if format_id is None:
            QMessageBox.information(
                self,
                "Sin formato",
                "Selecciona un formato guardado para precargarlo.",
            )
            return
        self.apply_saved_format(int(format_id), notify=True)

    def apply_saved_format(self, format_id: int, notify: bool = True) -> bool:
        row = self.database.get_service_format(format_id)
        if row is None:
            QMessageBox.warning(
                self,
                "Formato no disponible",
                "El formato seleccionado ya no existe en la base de datos.",
            )
            self.refresh_saved_formats()
            return False

        self.document_type.setCurrentText(
            str(row["document_type"] or "Cédula de Servicio")
        )
        line_mapping = (
            (self.validator_name, "validator_name"),
            (self.validator_role, "validator_role"),
            (self.validator_phone, "validator_phone"),
            (self.technician_name, "technician_name"),
        )
        for widget, key in line_mapping:
            value = str(row[key] or "").strip()
            if value:
                widget.setText(value)

        movement = str(row["movement_type"] or "").strip()
        if movement:
            self.movement_type.setCurrentText(movement)

        reported_issue = str(row["reported_issue"] or "").strip()
        if reported_issue:
            self.set_reported_issue_value(reported_issue)
        for widget, key in (
            (self.diagnosis, "diagnosis"),
            (self.solution, "solution"),
            (self.service_notes, "service_notes"),
        ):
            value = str(row[key] or "").strip()
            if value:
                widget.setPlainText(value)

        operates = str(row["equipment_operates"] or "").strip()
        condition = str(row["equipment_condition"] or "").strip()
        if operates:
            self.equipment_operates.setCurrentText(operates)
        if condition:
            self.equipment_condition.setCurrentText(condition)

        self.refresh_saved_formats(preserve_id=format_id)
        if notify:
            QMessageBox.information(
                self,
                "Formato precargado",
                f"Se aplicó el formato '{row['name']}'.\n\n"
                "El folio, la dependencia, el equipo, las fechas y los reportes "
                "se conservan como datos específicos de la orden.",
            )
        return True

    def apply_reported_issue_template(self, template_name: str):
        template = REPORTED_ISSUE_TEMPLATES.get(template_name, "")

        if template_name == "Entrada manual":
            self.reported_issue.setFocus()
            return

        # Cambiar la plantilla sustituye el contenido inmediatamente.
        # No se muestran confirmaciones intermedias durante la captura.
        self.reported_issue.setPlainText(template)
        self.reported_issue.setFocus()

    @staticmethod
    def detect_reported_issue_template(value: str) -> str:
        normalized = " ".join(str(value or "").split()).casefold()
        for name, template in REPORTED_ISSUE_TEMPLATES.items():
            if not template:
                continue
            template_normalized = " ".join(template.split()).casefold()
            if normalized == template_normalized:
                return name
        return "Entrada manual"

    def set_reported_issue_value(self, value: str):
        value = str(value or "")
        template_name = self.detect_reported_issue_template(value)
        self.reported_issue_template.blockSignals(True)
        self.reported_issue_template.setCurrentText(template_name)
        self.reported_issue_template.blockSignals(False)
        self.reported_issue.setPlainText(value)

    def _equipment_detail_widgets(self):
        return (
            self.auto_equipment_type,
            self.auto_brand,
            self.auto_model,
            self.auto_serial,
            self.auto_inventory_number,
            self.auto_ip,
            self.auto_hostname,
        )

    def equipment_mode_changed(self, manual: bool):
        self.equipment_filter.setEnabled(not manual)
        self.equipment.setEnabled(not manual)
        self.manual_equipment_status.setEnabled(manual)
        for widget in self._equipment_detail_widgets():
            widget.setReadOnly(not manual)

        if manual:
            self.equipment.blockSignals(True)
            self.equipment.setCurrentIndex(-1)
            self.equipment.blockSignals(False)
            for widget in self._equipment_detail_widgets():
                widget.clear()
            self.manual_equipment_status.setCurrentText("Activo")
            self.equipment_status.setText(
                "Captura los datos. Al guardar se verificará que no exista un duplicado."
            )
            self.auto_equipment_type.setFocus()
        else:
            self.refresh_equipment()

    @staticmethod
    def _dependency_search_text(row) -> str:
        return " ".join(str(row[key] or "") for key in (
            "name", "court", "tribunal", "office", "cta", "building", "floor",
            "city", "state", "street", "colony", "postal_code"
        )).lower()

    @staticmethod
    def _equipment_search_text(row) -> str:
        return " ".join(str(row[key] or "") for key in (
            "equipment_type", "brand", "model", "serial_number", "inventory_number",
            "ip_address", "hostname", "status"
        )).lower()

    def full_refresh(self):
        self.refresh_saved_formats()
        current_dependency = self.dependency.currentData()
        current_equipment = self.equipment.currentData()
        self.all_dependency_rows = self.database.dependency_choices_detailed()
        self.all_equipment_rows = self.database.equipment_choices_detailed()
        self.dependency_rows = {int(row["id"]): row for row in self.all_dependency_rows}
        self.equipment_rows = {int(row["id"]): row for row in self.all_equipment_rows}
        self.refresh_dependencies(preserve_id=current_dependency)
        self.refresh_equipment(preserve_id=current_equipment)
        self.refresh_history()

    def refresh_dependencies(self, *_args, preserve_id=None):
        if preserve_id is None:
            preserve_id = self.dependency.currentData()
        query = self.dependency_filter.text().strip().lower()
        rows = [
            row for row in self.all_dependency_rows
            if not query or query in self._dependency_search_text(row)
        ]

        self.dependency.blockSignals(True)
        self.dependency.clear()
        for row in rows:
            building = str(row["building"] or "").strip()
            floor = str(row["floor"] or "").strip()
            location = " · ".join(part for part in [building, f"Piso {floor}" if floor else ""] if part)
            label = f'{row["name"]} · {location}' if location else str(row["name"])
            self.dependency.addItem(label, int(row["id"]))
        if not rows:
            self.dependency.addItem("No hay dependencias que coincidan", None)
        index = self.dependency.findData(preserve_id)
        self.dependency.setCurrentIndex(index if index >= 0 else 0)
        self.dependency.blockSignals(False)
        self.dependency_status.setText(
            f"{len(rows)} de {len(self.all_dependency_rows)} dependencia(s)"
        )
        self.dependency_changed()

    def dependency_changed(self, *_args):
        dependency_id = self.dependency.currentData()
        changed = dependency_id != self._last_dependency_id
        self._last_dependency_id = dependency_id
        self.fill_dependency_details(apply_defaults=changed)
        self.refresh_equipment()

    def fill_dependency_details(self, apply_defaults: bool = True):
        dependency_id = self.dependency.currentData()
        row = self.dependency_rows.get(dependency_id)
        mapping = {
            self.auto_dependency_name: str(row["name"] or "") if row else "",
            self.auto_building: str(row["building"] or "") if row else "",
            self.auto_floor: str(row["floor"] or "") if row else "",
            self.auto_office: str(row["office"] or "") if row else "",
            self.auto_address: address_text(row),
            self.auto_city: str(row["city"] or "") if row else "",
            self.auto_state: str(row["state"] or "") if row else "",
            self.auto_cta: str(row["cta"] or "") if row else "",
            self.auto_phone: str(row["phone"] or "") if row else "",
            self.auto_email: str(row["email"] or "") if row else "",
        }
        for widget, value in mapping.items():
            widget.setText(value)

        if row and apply_defaults:
            cta = str(row["cta"] or "").strip()
            phone = str(row["phone"] or "").strip()
            self.responsible_name.setText(cta)
            self.validator_name.setText(cta)
            self.validator_phone.setText(phone)

    def refresh_equipment(self, *_args, preserve_id=None):
        if preserve_id is None:
            preserve_id = self.equipment.currentData()
        dependency_id = self.dependency.currentData()
        query = self.equipment_filter.text().strip().lower()
        rows = [
            row for row in self.all_equipment_rows
            if int(row["dependency_id"]) == dependency_id
            and (not query or query in self._equipment_search_text(row))
        ] if dependency_id is not None else []

        self.equipment.blockSignals(True)
        self.equipment.clear()
        for row in rows:
            serial = str(row["serial_number"] or "Sin serie")
            inventory = str(row["inventory_number"] or "").strip()
            brand_model = " ".join(
                part for part in [str(row["brand"] or "").strip(), str(row["model"] or "").strip()]
                if part
            )
            pieces = [serial, inventory, brand_model]
            self.equipment.addItem(" · ".join(piece for piece in pieces if piece), int(row["id"]))
        if not rows:
            text = (
                "La dependencia no tiene equipos registrados"
                if dependency_id is not None and not query
                else "No hay equipos que coincidan"
            )
            self.equipment.addItem(text, None)
        index = self.equipment.findData(preserve_id)
        self.equipment.setCurrentIndex(index if index >= 0 else 0)
        self.equipment.blockSignals(False)
        total_for_dependency = sum(
            1 for row in self.all_equipment_rows
            if dependency_id is not None and int(row["dependency_id"]) == dependency_id
        )
        if not self.manual_equipment.isChecked():
            self.equipment_status.setText(f"{len(rows)} de {total_for_dependency} equipo(s)")
            self.fill_equipment_details()

    def fill_equipment_details(self, *_args):
        if self.manual_equipment.isChecked():
            return
        equipment_id = self.equipment.currentData()
        row = self.equipment_rows.get(equipment_id)
        mapping = {
            self.auto_equipment_type: str(row["equipment_type"] or "") if row else "",
            self.auto_brand: str(row["brand"] or "") if row else "",
            self.auto_model: str(row["model"] or "") if row else "",
            self.auto_serial: str(row["serial_number"] or "") if row else "",
            self.auto_inventory_number: str(row["inventory_number"] or "") if row else "",
            self.auto_ip: str(row["ip_address"] or "") if row else "",
            self.auto_hostname: str(row["hostname"] or "") if row else "",
        }
        for widget, value in mapping.items():
            widget.setText(value)

    def update_document_fields(self):
        is_service = self.document_type.currentText() != "Mantenimiento Preventivo"
        self.dgti_report.setEnabled(is_service)
        self.provider_report.setEnabled(is_service)

    def _load_last_output_folder(self) -> str:
        try:
            if not self.settings_path.exists():
                return ""
            payload = json.loads(
                self.settings_path.read_text(encoding="utf-8")
            )
            folder = str(payload.get("last_output_folder") or "").strip()
            return folder if folder and Path(folder).is_dir() else ""
        except (OSError, ValueError, TypeError):
            return ""

    def _save_last_output_folder(self, folder: str) -> None:
        folder = str(folder or "").strip()
        if not folder:
            return
        try:
            self.settings_path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )
            self.settings_path.write_text(
                json.dumps(
                    {"last_output_folder": folder},
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            self.last_output_folder = folder
        except OSError:
            # The selected folder still works for the current session.
            self.last_output_folder = folder

    def _default_output_folder(self) -> str:
        candidates = [
            self.output_folder.text().strip(),
            self.last_output_folder,
            str(Path.home() / "Documents"),
            str(Path.home()),
        ]
        for candidate in candidates:
            if candidate and Path(candidate).is_dir():
                return candidate
        return str(Path.home())

    def choose_output_folder(self) -> bool:
        selected = QFileDialog.getExistingDirectory(
            self,
            "Seleccionar carpeta para guardar la cédula",
            self._default_output_folder(),
        )
        if not selected:
            return False

        self.output_folder.setText(selected)
        self._save_last_output_folder(selected)
        return True

    def _template_validation_message(self, path: Path) -> tuple[bool, str]:
        try:
            found, missing, unknown = validate_service_template(path)
        except Exception as error:
            return False, f"No se pudo leer la plantilla:\n{error}"
        lines = [f"Placeholders encontrados: {len(found)}"]
        if missing:
            lines.append("\nFaltan placeholders obligatorios:\n" + "\n".join(sorted(missing)))
        if unknown:
            lines.append("\nPlaceholders no reconocidos:\n" + "\n".join(sorted(unknown)))
        if not missing and not unknown:
            lines.append("\nLa plantilla es compatible con el Motor de Plantillas.")
        return not missing, "".join(lines)

    def validate_template(self):
        valid, message = self._template_validation_message(self.service_template_path)
        if valid:
            QMessageBox.information(self, "Plantilla válida", message)
        else:
            QMessageBox.warning(self, "Plantilla incompleta", message)

    def replace_template(self):
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "Seleccionar plantilla de Cédula de Servicio",
            str(self.folder),
            "Libro de Excel (*.xlsx)",
        )
        if not selected:
            return
        selected_path = Path(selected)
        valid, message = self._template_validation_message(selected_path)
        if not valid:
            answer = QMessageBox.question(
                self,
                "Plantilla incompleta",
                message + "\n\n¿Deseas instalarla de todos modos?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        try:
            if self.service_template_path.exists():
                backup = self.folder / "Formato de referencia - Cédula de Servicio_anterior.xlsx"
                shutil.copy2(self.service_template_path, backup)
            if selected_path.resolve() != self.service_template_path.resolve():
                shutil.copy2(selected_path, self.service_template_path)
        except Exception as error:
            QMessageBox.critical(self, "No se pudo reemplazar", str(error))
            return
        self.template_label.setText(str(self.service_template_path))
        QMessageBox.information(
            self,
            "Plantilla actualizada",
            "La plantilla activa fue reemplazada. La anterior quedó respaldada en la misma carpeta.",
        )

    def restore_default_template(self):
        if not self.default_service_template_path.exists():
            QMessageBox.critical(
                self, "No se pudo restaurar",
                f"No existe la plantilla incluida:\n{self.default_service_template_path}",
            )
            return
        answer = QMessageBox.question(
            self,
            "Restaurar plantilla",
            "Se reemplazará la plantilla activa por la versión incluida. ¿Continuar?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            if self.service_template_path.exists():
                backup = self.folder / "Formato de referencia - Cédula de Servicio_anterior.xlsx"
                shutil.copy2(self.service_template_path, backup)
            shutil.copy2(self.default_service_template_path, self.service_template_path)
        except Exception as error:
            QMessageBox.critical(self, "No se pudo restaurar", str(error))
            return
        QMessageBox.information(self, "Plantilla restaurada", "Se restauró la plantilla incluida.")

    def open_module_folder(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.folder.resolve())))

    def field_values(self):
        dependency_id = self.dependency.currentData()
        dependency = self.dependency_rows.get(dependency_id)
        if dependency is None:
            raise ValueError("Selecciona una dependencia registrada en el directorio.")

        manual = self.manual_equipment.isChecked()
        if manual:
            equipment_data = {
                "id": None,
                "dependency_id": int(dependency["id"]),
                "equipment_type": self.auto_equipment_type.text().strip(),
                "brand": self.auto_brand.text().strip(),
                "model": self.auto_model.text().strip(),
                "serial_number": self.auto_serial.text().strip(),
                "inventory_number": self.auto_inventory_number.text().strip(),
                "ip_address": self.auto_ip.text().strip(),
                "hostname": self.auto_hostname.text().strip(),
                "status": self.manual_equipment_status.currentText().strip() or "Activo",
                "notes": "",
            }
            equipment_id = None
        else:
            equipment_id = self.equipment.currentData()
            equipment = self.equipment_rows.get(equipment_id)
            if equipment is None:
                raise ValueError(
                    "Selecciona un equipo registrado o activa la captura manual para un equipo nuevo."
                )
            if int(equipment["dependency_id"]) != int(dependency["id"]):
                raise ValueError("El equipo seleccionado no pertenece a la dependencia elegida.")
            equipment_data = dict(equipment)
            equipment_id = int(equipment["id"])

        return {
            **equipment_data,
            "folio": self.folio.text().strip(),
            "document_type": self.document_type.currentText(),
            "manual_equipment": manual,
            "equipment_id": equipment_id,
            "dependency_id": int(dependency["id"]),
            "dependency_name": str(dependency["name"] or ""),
            "dependency_phone": str(dependency["phone"] or ""),
            "dependency_email": str(dependency["email"] or ""),
            "cta": str(dependency["cta"] or ""),
            "building": str(dependency["building"] or ""),
            "floor": str(dependency["floor"] or ""),
            "office": str(dependency["office"] or ""),
            "city": self.auto_city.text().strip(),
            "state": self.auto_state.text().strip(),
            "street": str(dependency["street"] or ""),
            "exterior_number": str(dependency["exterior_number"] or ""),
            "colony": str(dependency["colony"] or ""),
            "postal_code": str(dependency["postal_code"] or ""),
            "dgti_report": self.dgti_report.text().strip(),
            "provider_report": self.provider_report.text().strip(),
            "report_date": self.report_date.date().toString("dd/MM/yyyy"),
            "report_time": self.report_time.time().toString("HH:mm"),
            "responsible_name": self.responsible_name.text().strip(),
            "validator_name": self.validator_name.text().strip(),
            "validator_role": self.validator_role.text().strip(),
            "validator_phone": self.validator_phone.text().strip(),
            "movement_type": self.movement_type.currentText().strip(),
            "reported_issue": self.reported_issue.toPlainText().strip(),
            "diagnosis": self.diagnosis.toPlainText().strip(),
            "diagnosis_date": self.diagnosis_date.date().toString("dd/MM/yyyy"),
            "diagnosis_time": self.diagnosis_time.time().toString("HH:mm"),
            "solution": self.solution.toPlainText().strip(),
            "solution_date": self.solution_date.date().toString("dd/MM/yyyy"),
            "solution_time": self.solution_time.time().toString("HH:mm"),
            "service_notes": self.service_notes.toPlainText().strip(),
            "technician_name": self.technician_name.text().strip(),
            "output_path": self.current_output_path,
            "output_folder": self.output_folder.text().strip(),
            "equipment_operates": self.equipment_operates.currentText().strip(),
            "equipment_condition": self.equipment_condition.currentText().strip(),
        }

    def validate(self, values, require_output: bool = False):
        if not values["folio"]:
            self.folio.setFocus()
            raise ValueError("El folio es obligatorio, aunque puede escribirse con cualquier formato.")
        if values.get("manual_equipment"):
            if not values["equipment_type"]:
                self.auto_equipment_type.setFocus()
                raise ValueError("Indica el tipo del equipo nuevo.")
            if not any(
                str(values.get(key, "")).strip()
                for key in ("serial_number", "inventory_number", "hostname")
            ):
                self.auto_serial.setFocus()
                raise ValueError(
                    "Para registrar un equipo nuevo indica al menos su número de serie, "
                    "número de inventario o hostname."
                )
        if require_output and not values["output_folder"]:
            raise ValueError("Selecciona la carpeta donde se guardará la cédula.")

    def resolve_equipment(self, values):
        if not values.get("manual_equipment"):
            return values, ""

        equipment_values = {
            "dependency_id": values["dependency_id"],
            "equipment_type": values["equipment_type"],
            "brand": values["brand"],
            "model": values["model"],
            "serial_number": values["serial_number"],
            "inventory_number": values["inventory_number"],
            "ip_address": values["ip_address"],
            "hostname": values["hostname"],
            "status": values["status"] or "Activo",
            "notes": (
                f"Agregado automáticamente desde la orden de servicio {values['folio']}."
                if values.get("folio")
                else "Agregado automáticamente desde una orden de servicio."
            ),
        }

        duplicate = self.database.find_equipment_duplicate(equipment_values)
        if duplicate is not None:
            existing, matched_field = duplicate
            if int(existing["dependency_id"]) != int(values["dependency_id"]):
                raise ValueError(
                    f"El equipo coincide por {matched_field} con un registro existente "
                    f"asignado a la dependencia '{existing['dependency_name']}'. "
                    "No se creó un duplicado. Reasigna el equipo desde Inventario si fue trasladado."
                )
            equipment_id = int(existing["id"])
            notice = (
                f"Se detectó que el equipo ya existía por coincidencia de {matched_field}; "
                "se utilizó el registro existente y no se creó un duplicado."
            )
        else:
            equipment_id = self.database.save_equipment(equipment_values)
            notice = "El equipo nuevo fue agregado automáticamente al inventario."

        equipment = self.database.get_equipment_detailed(equipment_id)
        if equipment is None:
            raise ValueError("El equipo no pudo recuperarse después de registrarlo.")

        values.update(dict(equipment))
        values["equipment_id"] = equipment_id
        values["dependency_id"] = int(equipment["dependency_id"])
        values["manual_equipment"] = False

        self.all_equipment_rows = self.database.equipment_choices_detailed()
        self.equipment_rows = {int(row["id"]): row for row in self.all_equipment_rows}
        self.manual_equipment.blockSignals(True)
        self.manual_equipment.setChecked(False)
        self.manual_equipment.blockSignals(False)
        self.equipment_mode_changed(False)
        self.refresh_equipment(preserve_id=equipment_id)
        return values, notice

    def sync_dependency_city_state(self, values: dict) -> bool:
        """Persist edited city/state in the Directory location for this dependency."""
        dependency_id = int(values["dependency_id"])
        row = self.dependency_rows.get(dependency_id)
        city = str(values.get("city", "")).strip()
        state = str(values.get("state", "")).strip()
        old_city = str(row["city"] or "").strip() if row else ""
        old_state = str(row["state"] or "").strip() if row else ""
        if city == old_city and state == old_state:
            return False

        self.database.update_dependency_city_state(dependency_id, city, state)
        self.all_dependency_rows = self.database.dependency_choices_detailed()
        self.dependency_rows = {int(item["id"]): item for item in self.all_dependency_rows}
        return True

    def save_record(self):
        try:
            values = self.field_values()
            self.validate(values, require_output=False)
            self.sync_dependency_city_state(values)
            values, equipment_notice = self.resolve_equipment(values)
            self.current_id = self.database.save_service_order(values, self.current_id)
        except Exception as error:
            QMessageBox.warning(self, "No se pudo guardar", str(error))
            return
        self.refresh_history()
        message = "La orden de servicio quedó registrada."
        if equipment_notice:
            message += f"\n\n{equipment_notice}"
        QMessageBox.information(self, "Guardado", message)

    def show_document_preview(self):
        """Muestra los datos actuales antes de guardar o generar el archivo Excel."""
        try:
            values = self.field_values()
            self.validate(values, require_output=False)
        except Exception as error:
            QMessageBox.warning(self, "No se puede mostrar la vista previa", str(error))
            return

        def esc(value):
            text = str(value or "").strip()
            return html.escape(text).replace("\n", "<br>") or "<span style='color:#777'>Sin dato</span>"

        address_parts = [
            " ".join(part for part in [values.get("street", ""), values.get("exterior_number", "")] if part),
            f"Col. {values.get('colony', '')}" if values.get("colony") else "",
            f"C.P. {values.get('postal_code', '')}" if values.get("postal_code") else "",
            values.get("building", ""),
            f"Piso {values.get('floor', '')}" if values.get("floor") else "",
            values.get("office", ""),
        ]
        address = ", ".join(part for part in address_parts if str(part).strip())

        preview_html = f"""
        <html><head><style>
            body {{ font-family: Arial, sans-serif; background:#ececec; margin:18px; }}
            .sheet {{ background:white; max-width:820px; margin:auto; padding:28px;
                      border:1px solid #aaa; box-shadow:0 2px 10px rgba(0,0,0,.18); }}
            h1 {{ text-align:center; font-size:20px; margin:4px 0 18px; }}
            h2 {{ font-size:13px; background:#e5e7eb; border:1px solid #777;
                  padding:6px; margin:14px 0 0; text-transform:uppercase; }}
            table {{ width:100%; border-collapse:collapse; }}
            td {{ border:1px solid #888; padding:6px; vertical-align:top; font-size:12px; }}
            .label {{ width:31%; font-weight:bold; background:#f5f5f5; }}
            .large {{ min-height:70px; }}
            .note {{ color:#555; font-size:11px; margin-top:14px; text-align:center; }}
        </style></head><body><div class='sheet'>
            <h1>{esc(values.get('document_type'))}</h1>
            <table>
                <tr><td class='label'>Reporte DGTI</td><td>{esc(values.get('dgti_report'))}</td>
                    <td class='label'>Reporte del prestador</td><td>{esc(values.get('provider_report') or values.get('folio'))}</td></tr>
                <tr><td class='label'>Fecha y hora</td><td colspan='3'>{esc(values.get('report_date'))} — {esc(values.get('report_time'))}</td></tr>
            </table>
            <h2>Responsable y dependencia</h2>
            <table>
                <tr><td class='label'>Responsable</td><td>{esc(values.get('responsible_name'))}</td></tr>
                <tr><td class='label'>Dependencia</td><td>{esc(values.get('dependency_name'))}</td></tr>
                <tr><td class='label'>Domicilio</td><td>{esc(address)}</td></tr>
                <tr><td class='label'>Ciudad / Estado</td><td>{esc(' / '.join(x for x in [values.get('city',''), values.get('state','')] if x))}</td></tr>
                <tr><td class='label'>Validador</td><td>{esc(values.get('validator_name'))}</td></tr>
                <tr><td class='label'>Cargo / teléfono</td><td>{esc(values.get('validator_role'))} — {esc(values.get('validator_phone'))}</td></tr>
                <tr><td class='label'>Movimiento</td><td>{esc(values.get('movement_type'))}</td></tr>
            </table>
            <h2>Equipo</h2>
            <table>
                <tr><td class='label'>Tipo</td><td>{esc(values.get('equipment_type'))}</td><td class='label'>Marca</td><td>{esc(values.get('brand'))}</td></tr>
                <tr><td class='label'>Modelo</td><td>{esc(values.get('model'))}</td><td class='label'>Serie</td><td>{esc(values.get('serial_number'))}</td></tr>
                <tr><td class='label'>Inventario</td><td>{esc(values.get('inventory_number'))}</td><td class='label'>Hostname / IP</td><td>{esc(values.get('hostname'))} / {esc(values.get('ip_address'))}</td></tr>
            </table>
            <h2>Falla reportada</h2><table><tr><td class='large'>{esc(values.get('reported_issue'))}</td></tr></table>
            <h2>Diagnóstico</h2><table><tr><td class='large'>{esc(values.get('diagnosis'))}<br><br><b>Inicio:</b> {esc(values.get('diagnosis_date'))} {esc(values.get('diagnosis_time'))}</td></tr></table>
            <h2>Solución o servicio realizado</h2><table><tr><td class='large'>{esc(values.get('solution'))}<br><br><b>Fin:</b> {esc(values.get('solution_date'))} {esc(values.get('solution_time'))}</td></tr></table>
            <h2>Observaciones</h2><table><tr><td class='large'>{esc(values.get('service_notes') or 'Sin Observaciones')}</td></tr></table>
            <h2>Firmas</h2><table><tr><td class='label'>Técnico</td><td>{esc(values.get('technician_name'))}</td><td class='label'>Responsable</td><td>{esc(values.get('validator_name') or values.get('responsible_name'))}</td></tr></table>
            <p class='note'>Vista previa del contenido. El archivo final conservará el formato y logotipos de la plantilla Excel configurada.</p>
        </div></body></html>
        """

        dialog = QDialog(self)
        dialog.setWindowTitle("Vista previa de cédula")
        dialog.resize(940, 760)
        layout = QVBoxLayout(dialog)
        browser = QTextBrowser(dialog)
        browser.setHtml(preview_html)
        layout.addWidget(browser, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        buttons.clicked.connect(dialog.accept)
        layout.addWidget(buttons)
        dialog.exec()

    def generate_document(self):
        answer = QMessageBox.question(
            self,
            "Generar cédula",
            "¿Deseas guardar la información y generar la cédula?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            # Validate the form first, but do not fail merely because the output
            # folder has not been chosen yet.
            values = self.field_values()
            self.validate(values, require_output=False)

            if not values["output_folder"]:
                selected = self.choose_output_folder()
                if not selected:
                    # The user cancelled the folder dialog. This is not an
                    # application error and no record is created.
                    return
                values = self.field_values()

            self.validate(values, require_output=True)
            self._save_last_output_folder(values["output_folder"])
            self.sync_dependency_city_state(values)

            values, equipment_notice = self.resolve_equipment(values)
            self.current_id = self.database.save_service_order(
                values,
                self.current_id,
            )
            output = generate_service_document(
                self.template_path,
                Path(values["output_folder"]),
                values,
            )
            self.current_output_path = str(output)
            self.database.update_service_order_output(
                self.current_id,
                self.current_output_path,
            )
        except Exception as error:
            QMessageBox.critical(
                self,
                "No se pudo generar la cédula",
                str(error),
            )
            return

        self.refresh_history()
        extra = f"\n\n{equipment_notice}" if equipment_notice else ""
        answer = QMessageBox.question(
            self,
            "Cédula generada",
            f"El archivo se guardó en:\n\n{output}{extra}\n\n¿Abrirlo ahora?",
        )
        if answer == QMessageBox.StandardButton.Yes:
            QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(output))
            )

    def refresh_history(self):
        rows = self.database.list_service_orders(self.search.text())
        self.order_rows = {int(row["id"]): row for row in rows}
        self.table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            values = [
                str(row["created_at"] or ""),
                str(row["folio"] or ""),
                str(row["document_type"] or ""),
                str(row["serial_number"] or ""),
                str(row["model"] or ""),
                str(row["dependency_name"] or ""),
                str(row["output_path"] or ""),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, int(row["id"]))
                self.table.setItem(row_index, column, item)
        self.table.resizeColumnsToContents()

    @staticmethod
    def _set_date(widget: QDateEdit, value: str):
        parsed = QDate.fromString(str(value or ""), "dd/MM/yyyy")
        widget.setDate(parsed if parsed.isValid() else QDate.currentDate())

    @staticmethod
    def _set_time(widget: QTimeEdit, value: str):
        parsed = QTime.fromString(str(value or ""), "HH:mm")
        widget.setTime(parsed if parsed.isValid() else QTime.currentTime())

    def load_selected_order(self):
        selected = self.table.selectedItems()
        if not selected:
            return
        order_id = int(selected[0].data(Qt.ItemDataRole.UserRole))
        row = self.order_rows.get(order_id)
        if row is None:
            return
        self.current_id = order_id
        self.current_output_path = str(row["output_path"] or "")
        self.folio.setText(str(row["folio"] or ""))
        self.document_type.setCurrentText(str(row["document_type"] or "Cédula de Servicio"))
        self.manual_equipment.setChecked(False)

        dependency_index = self.dependency.findData(row["dependency_id"])
        if dependency_index < 0:
            self.dependency_filter.clear()
            self.refresh_dependencies(preserve_id=row["dependency_id"])
            dependency_index = self.dependency.findData(row["dependency_id"])
        if dependency_index >= 0:
            self.dependency.setCurrentIndex(dependency_index)

        self.equipment_filter.clear()
        self.refresh_equipment(preserve_id=row["equipment_id"])
        equipment_index = self.equipment.findData(row["equipment_id"])
        if equipment_index >= 0:
            self.equipment.setCurrentIndex(equipment_index)

        self.dgti_report.setText(str(row["dgti_report"] or ""))
        self.provider_report.setText(str(row["provider_report"] or ""))
        self._set_date(self.report_date, row["report_date"])
        self._set_time(self.report_time, row["report_time"])
        self.responsible_name.setText(str(row["responsible_name"] or ""))
        self.validator_name.setText(str(row["validator_name"] or ""))
        self.validator_role.setText(str(row["validator_role"] or ""))
        self.validator_phone.setText(str(row["validator_phone"] or ""))
        self.movement_type.setCurrentText(str(row["movement_type"] or ""))
        self.set_reported_issue_value(
            str(row["reported_issue"] or "")
        )
        self.diagnosis.setPlainText(str(row["diagnosis"] or ""))
        self._set_date(self.diagnosis_date, row["diagnosis_date"])
        self._set_time(self.diagnosis_time, row["diagnosis_time"])
        self.solution.setPlainText(str(row["solution"] or ""))
        self._set_date(self.solution_date, row["solution_date"])
        self._set_time(self.solution_time, row["solution_time"])
        self.service_notes.setPlainText(str(row["service_notes"] or ""))
        self.technician_name.setText(str(row["technician_name"] or ""))
        self.equipment_operates.setCurrentText(str(row["equipment_operates"] or "Sí"))
        self.equipment_condition.setCurrentText(str(row["equipment_condition"] or "No"))
        if self.current_output_path:
            previous_folder = str(Path(self.current_output_path).parent)
            self.output_folder.setText(previous_folder)
            self._save_last_output_folder(previous_folder)

    def clear_form(self):
        self.current_id = None
        self.current_output_path = ""
        self.table.clearSelection()
        self.folio.clear()
        self.dgti_report.clear()
        self.provider_report.clear()
        self.validator_role.clear()
        self.movement_type.setCurrentIndex(0)
        self.reported_issue_template.blockSignals(True)
        self.reported_issue_template.setCurrentText("Entrada manual")
        self.reported_issue_template.blockSignals(False)
        self.reported_issue.clear()
        self.diagnosis.clear()
        self.solution.clear()
        self.service_notes.clear()
        self.technician_name.clear()
        self.report_date.setDate(QDate.currentDate())
        self.report_time.setTime(QTime.currentTime())
        self.diagnosis_date.setDate(QDate.currentDate())
        self.diagnosis_time.setTime(QTime.currentTime())
        self.solution_date.setDate(QDate.currentDate())
        self.solution_time.setTime(QTime.currentTime())
        self.equipment_operates.setCurrentText("Sí")
        self.equipment_condition.setCurrentText("No")
        self.manual_equipment.setChecked(False)
        self.manual_equipment_status.setCurrentText("Activo")
        self.fill_dependency_details(apply_defaults=True)
        self.fill_equipment_details()
        self.folio.setFocus()

    def delete_record(self):
        if self.current_id is None:
            QMessageBox.information(self, "Sin selección", "Selecciona una orden registrada.")
            return
        answer = QMessageBox.question(
            self,
            "Eliminar registro",
            "Esto elimina el registro de la base, pero no borra el archivo Excel generado.\n\n¿Continuar?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.database.delete_service_order(self.current_id)
        except Exception as error:
            QMessageBox.warning(self, "No se pudo eliminar", str(error))
            return
        self.clear_form()
        self.refresh_history()

    def open_selected_file(self):
        selected = self.table.selectedItems()
        if not selected:
            QMessageBox.information(self, "Sin selección", "Selecciona una orden.")
            return
        order_id = int(selected[0].data(Qt.ItemDataRole.UserRole))
        row = self.order_rows.get(order_id)
        path = Path(str(row["output_path"] or "")) if row else None
        if not path or not path.exists():
            QMessageBox.warning(self, "Archivo no encontrado", "La orden no tiene un archivo existente asociado.")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
