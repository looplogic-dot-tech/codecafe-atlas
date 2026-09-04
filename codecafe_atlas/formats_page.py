from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
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
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .database import Database
from .ui_helpers import line_edit, notes_edit, page_header


class FormatsPage(QWidget):
    """Catalog of reusable service-order formats stored in SQLite."""

    formats_changed = Signal()
    format_requested = Signal(int)

    def __init__(self, database: Database):
        super().__init__()
        self.database = database
        self.current_id: int | None = None
        self.rows: dict[int, object] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 18, 22, 22)
        root.setSpacing(12)
        root.addWidget(page_header(
            "Administración de formatos",
            "Biblioteca de plantillas y formatos. Selecciona un formato para ver o editar su configuración.",
        ))

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        root.addWidget(splitter, 1)

        # Catalog
        catalog = QWidget()
        catalog_layout = QVBoxLayout(catalog)
        catalog_layout.setContentsMargins(0, 0, 10, 0)
        catalog_layout.setSpacing(9)

        search_row = QHBoxLayout()
        self.search = line_edit("Buscar por nombre, tipo, descripción o contenido…")
        self.search.textChanged.connect(self.refresh)
        search_row.addWidget(self.search, 1)
        refresh_button = QPushButton("Actualizar")
        refresh_button.clicked.connect(self.refresh)
        search_row.addWidget(refresh_button)
        catalog_layout.addLayout(search_row)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels([
            "Nombre", "Tipo", "Estado", "Actualizado",
        ])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self.load_selected)
        catalog_layout.addWidget(self.table, 1)

        catalog_actions = QHBoxLayout()
        new_catalog_button = QPushButton("Nuevo formato")
        new_catalog_button.clicked.connect(self.clear_form)
        use_button = QPushButton("Usar en orden de servicio")
        use_button.setObjectName("primaryButton")
        use_button.clicked.connect(self.request_current_format)
        duplicate_button = QPushButton("Duplicar")
        duplicate_button.clicked.connect(self.duplicate_current)
        catalog_actions.addWidget(new_catalog_button)
        catalog_actions.addWidget(use_button)
        catalog_actions.addWidget(duplicate_button)
        catalog_layout.addLayout(catalog_actions)
        splitter.addWidget(catalog)

        # Detail/editor: hidden until a format is selected or New format is pressed.
        right_host = QWidget()
        right_layout = QVBoxLayout(right_host)
        right_layout.setContentsMargins(10, 0, 0, 0)
        self.empty_detail = QLabel(
            "Selecciona un formato de la biblioteca para ver o editar su configuración.\n\n"
            "También puedes usar Nuevo formato para crear una nueva plantilla."
        )
        self.empty_detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_detail.setWordWrap(True)
        self.empty_detail.setObjectName("mutedLabel")
        right_layout.addWidget(self.empty_detail, 1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        editor_host = QWidget()
        editor_root = QVBoxLayout(editor_host)
        editor_root.setContentsMargins(10, 0, 0, 0)
        editor_root.setSpacing(10)

        identity_box = QGroupBox("Identidad del formato")
        identity_form = QFormLayout(identity_box)
        self.name = line_edit("Nombre único del formato")
        self.document_type = QComboBox()
        self.document_type.addItems([
            "Cédula de Servicio",
            "Mantenimiento Preventivo",
            "Dictaminación",
        ])
        self.description = notes_edit("Descripción breve y propósito del formato")
        self.description.setMaximumHeight(75)
        self.active = QCheckBox("Disponible para precargar órdenes")
        self.active.setChecked(True)
        identity_form.addRow("Nombre *", self.name)
        identity_form.addRow("Tipo de documento", self.document_type)
        identity_form.addRow("Descripción", self.description)
        identity_form.addRow("Estado", self.active)

        validation_box = QGroupBox("Validación y movimiento")
        validation_form = QFormLayout(validation_box)
        self.validator_name = line_edit("Servidor público que valida")
        self.validator_role = line_edit("Cargo")
        self.validator_phone = line_edit("Teléfono")
        self.movement_type = QComboBox()
        self.movement_type.addItems([
            "", "Sustitución", "Actualización", "Reubicación",
            "Incremento", "Disminución",
        ])
        validation_form.addRow("Validador", self.validator_name)
        validation_form.addRow("Cargo", self.validator_role)
        validation_form.addRow("Teléfono", self.validator_phone)
        validation_form.addRow("Movimiento", self.movement_type)

        service_box = QGroupBox("Datos que se precargarán")
        service_form = QFormLayout(service_box)
        self.reported_issue = self._large_notes("Falla reportada")
        self.diagnosis = self._large_notes("Diagnóstico")
        self.solution = self._large_notes("Solución o servicio realizado")
        self.service_notes = self._large_notes("Observaciones")
        self.technician_name = line_edit("Nombre del técnico")
        self.equipment_operates = QComboBox()
        self.equipment_operates.addItems(["Sí", "No", "No aplica"])
        self.equipment_condition = QComboBox()
        self.equipment_condition.addItems(["No", "Sí", "No aplica"])
        service_form.addRow("Falla reportada", self.reported_issue)
        service_form.addRow("Diagnóstico", self.diagnosis)
        service_form.addRow("Solución / servicio", self.solution)
        service_form.addRow("Observaciones", self.service_notes)
        service_form.addRow("Técnico", self.technician_name)
        service_form.addRow("¿Opera adecuadamente?", self.equipment_operates)
        service_form.addRow("¿Rayaduras o golpes?", self.equipment_condition)

        editor_root.addWidget(identity_box)
        editor_root.addWidget(validation_box)
        editor_root.addWidget(service_box)

        actions = QHBoxLayout()
        new_button = QPushButton("Nuevo / limpiar")
        new_button.clicked.connect(self.clear_form)
        delete_button = QPushButton("Eliminar")
        delete_button.setObjectName("dangerButton")
        delete_button.clicked.connect(self.delete_current)
        save_button = QPushButton("Guardar formato")
        save_button.setObjectName("primaryButton")
        save_button.clicked.connect(self.save_current)
        actions.addWidget(new_button)
        actions.addStretch(1)
        actions.addWidget(delete_button)
        actions.addWidget(save_button)
        editor_root.addLayout(actions)
        editor_root.addStretch(1)

        scroll.setWidget(editor_host)
        self.editor_scroll = scroll
        right_layout.addWidget(scroll, 1)
        splitter.addWidget(right_host)
        splitter.setSizes([530, 760])

        self.refresh()
        self._show_library_placeholder()

    @staticmethod
    def _large_notes(placeholder: str) -> QTextEdit:
        widget = notes_edit(placeholder)
        widget.setMinimumHeight(88)
        widget.setMaximumHeight(150)
        return widget

    def _show_library_placeholder(self) -> None:
        self.current_id = None
        self.table.clearSelection()
        self.editor_scroll.setVisible(False)
        self.empty_detail.setVisible(True)

    def _show_editor(self) -> None:
        self.empty_detail.setVisible(False)
        self.editor_scroll.setVisible(True)

    def refresh(self, *_args, preserve_id: int | None = None) -> None:
        if preserve_id is None:
            preserve_id = self.current_id
        rows = self.database.list_service_formats(self.search.text())
        self.rows = {int(row["id"]): row for row in rows}
        self.table.blockSignals(True)
        self.table.setRowCount(len(rows))
        selected_row = -1
        for row_index, row in enumerate(rows):
            format_id = int(row["id"])
            values = [
                str(row["name"] or ""),
                str(row["document_type"] or ""),
                "Activo" if int(row["active"] or 0) else "Inactivo",
                str(row["updated_at"] or ""),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, format_id)
                self.table.setItem(row_index, column, item)
            if format_id == preserve_id:
                selected_row = row_index
        self.table.blockSignals(False)
        self.table.resizeColumnsToContents()
        if selected_row >= 0:
            self.table.selectRow(selected_row)

    def selected_id(self) -> int | None:
        selected = self.table.selectedItems()
        if not selected:
            return None
        value = selected[0].data(Qt.ItemDataRole.UserRole)
        return int(value) if value is not None else None

    def load_selected(self) -> None:
        format_id = self.selected_id()
        if format_id is None:
            return
        row = self.rows.get(format_id)
        if row is None:
            row = self.database.get_service_format(format_id)
        if row is None:
            return
        self.current_id = format_id
        self._show_editor()
        self.name.setText(str(row["name"] or ""))
        self.document_type.setCurrentText(str(row["document_type"] or "Cédula de Servicio"))
        self.description.setPlainText(str(row["description"] or ""))
        self.validator_name.setText(str(row["validator_name"] or ""))
        self.validator_role.setText(str(row["validator_role"] or ""))
        self.validator_phone.setText(str(row["validator_phone"] or ""))
        self.movement_type.setCurrentText(str(row["movement_type"] or ""))
        self.reported_issue.setPlainText(str(row["reported_issue"] or ""))
        self.diagnosis.setPlainText(str(row["diagnosis"] or ""))
        self.solution.setPlainText(str(row["solution"] or ""))
        self.service_notes.setPlainText(str(row["service_notes"] or ""))
        self.technician_name.setText(str(row["technician_name"] or ""))
        self.equipment_operates.setCurrentText(str(row["equipment_operates"] or "Sí"))
        self.equipment_condition.setCurrentText(str(row["equipment_condition"] or "No"))
        self.active.setChecked(bool(row["active"]))

    def values(self) -> dict[str, object]:
        return {
            "name": self.name.text().strip(),
            "document_type": self.document_type.currentText().strip(),
            "description": self.description.toPlainText().strip(),
            "validator_name": self.validator_name.text().strip(),
            "validator_role": self.validator_role.text().strip(),
            "validator_phone": self.validator_phone.text().strip(),
            "movement_type": self.movement_type.currentText().strip(),
            "reported_issue": self.reported_issue.toPlainText().strip(),
            "diagnosis": self.diagnosis.toPlainText().strip(),
            "solution": self.solution.toPlainText().strip(),
            "service_notes": self.service_notes.toPlainText().strip(),
            "technician_name": self.technician_name.text().strip(),
            "equipment_operates": self.equipment_operates.currentText().strip(),
            "equipment_condition": self.equipment_condition.currentText().strip(),
            "active": self.active.isChecked(),
        }

    def save_current(self) -> None:
        try:
            format_id = self.database.save_service_format(self.values(), self.current_id)
        except Exception as error:
            QMessageBox.warning(self, "No se pudo guardar", str(error))
            return
        self.current_id = format_id
        self.refresh(preserve_id=format_id)
        self.formats_changed.emit()
        QMessageBox.information(
            self,
            "Formato guardado",
            "El formato quedó guardado en la base de datos.",
        )

    def clear_form(self) -> None:
        self.current_id = None
        self._show_editor()
        self.table.clearSelection()
        self.name.clear()
        self.document_type.setCurrentText("Cédula de Servicio")
        self.description.clear()
        self.validator_name.clear()
        self.validator_role.clear()
        self.validator_phone.clear()
        self.movement_type.setCurrentIndex(0)
        self.reported_issue.clear()
        self.diagnosis.clear()
        self.solution.clear()
        self.service_notes.clear()
        self.technician_name.clear()
        self.equipment_operates.setCurrentText("Sí")
        self.equipment_condition.setCurrentText("No")
        self.active.setChecked(True)
        self.name.setFocus()

    def duplicate_current(self) -> None:
        format_id = self.selected_id()
        if format_id is None:
            QMessageBox.information(self, "Sin selección", "Selecciona un formato para duplicarlo.")
            return
        self.load_selected()
        original_name = self.name.text().strip()
        self.current_id = None
        self.table.clearSelection()
        self.name.setText(f"{original_name} - copia")
        self.name.selectAll()
        self.name.setFocus()

    def delete_current(self) -> None:
        if self.current_id is None:
            QMessageBox.information(self, "Sin selección", "Selecciona un formato registrado.")
            return
        answer = QMessageBox.question(
            self,
            "Eliminar formato",
            "El formato se eliminará de la base de datos. Las órdenes ya guardadas no se modificarán.\n\n¿Continuar?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.database.delete_service_format(self.current_id)
        except Exception as error:
            QMessageBox.warning(self, "No se pudo eliminar", str(error))
            return
        self.refresh()
        self._show_library_placeholder()
        self.formats_changed.emit()

    def request_current_format(self) -> None:
        format_id = self.selected_id() or self.current_id
        if format_id is None:
            QMessageBox.information(self, "Sin selección", "Selecciona un formato para precargarlo.")
            return
        row = self.database.get_service_format(format_id)
        if row is None:
            QMessageBox.warning(self, "Formato no disponible", "El formato ya no existe.")
            self.refresh()
            return
        if not int(row["active"] or 0):
            answer = QMessageBox.question(
                self,
                "Formato inactivo",
                "El formato está marcado como inactivo. ¿Deseas usarlo de todos modos?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self.format_requested.emit(format_id)
