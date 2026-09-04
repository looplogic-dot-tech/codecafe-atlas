from __future__ import annotations

from collections import defaultdict
from datetime import date

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .database import Database
from .ui_helpers import line_edit, notes_edit


FLOOR_ORDER = {
    "planta baja": 0,
    "pb": 0,
    "primer piso": 1,
    "1": 1,
    "1er piso": 1,
    "segundo piso": 2,
    "2": 2,
    "tercer piso": 3,
    "3": 3,
    "cuarto piso": 4,
    "4": 4,
    "quinto piso": 5,
    "5": 5,
}


def _floor_key(value: str) -> tuple[int, str]:
    text = (value or "").strip().lower()
    return FLOOR_ORDER.get(text, 99), text


def _address(row) -> str:
    keys = set(row.keys()) if hasattr(row, "keys") else set()
    if "building_address" in keys:
        canonical = str(row["building_address"] or "").strip()
        if canonical:
            return canonical
    street_number = " ".join(
        part for part in (str(row["street"] or "").strip(), str(row["exterior_number"] or "").strip()) if part
    )
    parts = [
        street_number,
        str(row["colony"] or "").strip(),
        f'C.P. {row["postal_code"]}' if row["postal_code"] else "",
        str(row["city"] or "").strip(),
        str(row["state"] or "").strip(),
    ]
    return ", ".join(part for part in parts if part) or "Dirección no especificada"


def _entry_type(row) -> str:
    if row["court"]:
        return "Juzgado"
    if row["tribunal"]:
        return "Tribunal"
    if row["office"]:
        return "Oficina"
    name = str(row["name"] or "").lower()
    if "juzgado" in name:
        return "Juzgado"
    if "tribunal" in name:
        return "Tribunal"
    return "Dependencia"


class DependencyDialog(QDialog):
    def __init__(self, database: Database, parent=None):
        super().__init__(parent)
        self.database = database
        self._building_rows = []
        self._building_by_name = {}
        self.setModal(True)
        self.setWindowTitle("Información de la dependencia")

        # En Windows la escala de pantalla puede hacer que el formulario sea
        # más alto que el área disponible. La ventana queda redimensionable,
        # con botón de maximizar y un tamaño inicial adaptado a la pantalla.
        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowType.WindowMinMaxButtonsHint
        )
        self.setMinimumSize(560, 460)
        self.resize(760, 760)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QWidget()
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(22, 18, 22, 14)
        header_layout.setSpacing(5)

        title = QLabel("Información de la dependencia")
        title.setObjectName("dialogTitle")
        subtitle = QLabel(
            "Los cambios se guardan en la base portátil y se comparten "
            "con inventario y órdenes de servicio."
        )
        subtitle.setObjectName("pageSubtitle")
        subtitle.setWordWrap(True)
        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        root.addWidget(header)

        # Solo el formulario se desplaza. Los botones permanecen siempre
        # visibles en la parte inferior.
        self.form_scroll = QScrollArea()
        self.form_scroll.setWidgetResizable(True)
        self.form_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.form_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.form_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )

        form_container = QWidget()
        form_container.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        form_container_layout = QVBoxLayout(form_container)
        form_container_layout.setContentsMargins(22, 8, 22, 18)

        form = QFormLayout()
        form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow
        )
        form.setRowWrapPolicy(
            QFormLayout.RowWrapPolicy.WrapLongRows
        )
        form.setLabelAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        form.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(10)

        building_combo = QComboBox()
        building_combo.setEditable(True)
        building_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        building_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        building_combo.lineEdit().setPlaceholderText("Selecciona un edificio existente o escribe uno nuevo")

        self.fields = {
            "name": line_edit("Nombre completo de la dependencia"),
            "court": line_edit("Juzgado, si aplica"),
            "tribunal": line_edit("Tribunal, si aplica"),
            "office": line_edit("Oficina o departamento"),
            "cta": line_edit("CTA / encargado"),
            "phone": line_edit("Teléfono"),
            "email": line_edit("Correo electrónico"),
            "building": building_combo,
            "floor": line_edit("Piso"),
            "street": line_edit("Calle o avenida"),
            "exterior_number": line_edit("Número exterior"),
            "colony": line_edit("Colonia"),
            "postal_code": line_edit("Código postal"),
            "city": line_edit("Ciudad"),
            "state": line_edit("Estado"),
            "notes": notes_edit("Información adicional"),
        }

        for widget in self.fields.values():
            widget.setMinimumWidth(260)

        self.fields["notes"].setMinimumHeight(100)
        self.fields["notes"].setMaximumHeight(180)

        form.addRow("Dependencia *", self.fields["name"])
        form.addRow("Oficina", self.fields["office"])
        form.addRow("CTA / encargado", self.fields["cta"])
        form.addRow("Teléfono", self.fields["phone"])
        form.addRow("Correo", self.fields["email"])

        building_row = QWidget()
        building_layout = QHBoxLayout(building_row)
        building_layout.setContentsMargins(0, 0, 0, 0)
        building_layout.setSpacing(8)
        building_layout.addWidget(self.fields["building"], 1)
        self.add_building_inline_button = QPushButton("＋ Nuevo edificio")
        self.add_building_inline_button.setObjectName("softButton")
        self.add_building_inline_button.setToolTip("Crear un edificio nuevo con su dirección completa")
        building_layout.addWidget(self.add_building_inline_button)
        form.addRow("Edificio *", building_row)
        form.addRow("Piso", self.fields["floor"])
        inherited = QLabel("Dirección heredada del edificio. Para modificarla, usa Editar edificio.")
        inherited.setWordWrap(True)
        inherited.setObjectName("pageSubtitle")
        inherited.setMinimumHeight(34)
        form.addRow(inherited)
        for key in ("street","exterior_number","colony","postal_code","city","state"):
            self.fields[key].setReadOnly(True)
            self.fields[key].setPlaceholderText("Heredado del edificio")
        form.addRow("Calle", self.fields["street"])
        form.addRow("Número", self.fields["exterior_number"])
        form.addRow("Colonia", self.fields["colony"])
        form.addRow("C.P.", self.fields["postal_code"])
        form.addRow("Ciudad", self.fields["city"])
        form.addRow("Estado", self.fields["state"])
        form.addRow("Notas", self.fields["notes"])

        form_container_layout.addLayout(form)
        form_container_layout.addStretch(1)
        self.form_scroll.setWidget(form_container)
        root.addWidget(self.form_scroll, 1)

        footer = QFrame()
        footer.setObjectName("dialogFooter")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(22, 12, 22, 14)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Save
        )
        save_button = self.buttons.button(
            QDialogButtonBox.StandardButton.Save
        )
        save_button.setText("Guardar entrada")
        save_button.setObjectName("primaryButton")
        self.buttons.button(
            QDialogButtonBox.StandardButton.Cancel
        ).setText("Cancelar")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        footer_layout.addStretch(1)
        footer_layout.addWidget(self.buttons)
        root.addWidget(footer)

        self._reload_buildings()
        self.fields["building"].currentTextChanged.connect(self._sync_inherited_address)
        self.add_building_inline_button.clicked.connect(self._create_building_inline)

        # Ajusta el tamaño inicial a la pantalla disponible, especialmente útil
        # con escalado de 125 % o 150 % en Windows.
        screen = self.screen()
        if screen is not None:
            available = screen.availableGeometry()
            width = min(820, max(580, int(available.width() * 0.72)))
            height = min(820, max(520, int(available.height() * 0.88)))
            self.resize(width, height)

    def showEvent(self, event):
        super().showEvent(event)
        # Empieza siempre en la parte superior del formulario.
        self.form_scroll.verticalScrollBar().setValue(0)

    def _reload_buildings(self, selected_name: str = "") -> None:
        combo = self.fields["building"]
        current = selected_name or combo.currentText().strip()
        self._building_rows = list(self.database.list_buildings())
        self._building_by_name = {str(row["name"] or "").strip().casefold(): row for row in self._building_rows}
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("")
        for row in self._building_rows:
            combo.addItem(str(row["name"] or "").strip(), int(row["id"]))
        combo.setCurrentText(current)
        combo.blockSignals(False)
        self._sync_inherited_address(combo.currentText())

    def _sync_inherited_address(self, building_name: str) -> None:
        row = self._building_by_name.get(str(building_name or "").strip().casefold())
        for key in ("street", "exterior_number", "colony", "postal_code", "city", "state"):
            value = str(row[key] or "") if row is not None else ""
            self.fields[key].setText(value)

    def _confirm_new_building_name(self, name: str) -> bool:
        name = str(name or "").strip()
        if not name:
            QMessageBox.warning(self, "Falta edificio", "Selecciona un edificio existente o crea uno nuevo.")
            return False
        exact = self._building_by_name.get(name.casefold())
        if exact is not None:
            return True
        matches = self.database.similar_buildings(name)
        equivalent = next((item for item in matches if float(item["score"]) >= 0.999), None)
        if equivalent is not None:
            QMessageBox.warning(
                self,
                "Edificio ya existente",
                f'“{name}” equivale al edificio existente “{equivalent["name"]}”.\n\n'
                "Atlas no creará un duplicado. Selecciona el edificio existente en la lista.",
            )
            self.fields["building"].setCurrentText(str(equivalent["name"]))
            return False
        if not matches:
            return True
        lines = [f"• {item['name']} ({item['score']:.0%} similar)" for item in matches[:5]]
        answer = QMessageBox.question(
            self,
            "Posible edificio duplicado",
            "Atlas encontró nombres de edificio muy similares:\n\n" + "\n".join(lines) +
            "\n\n¿Confirmas que deseas usar un edificio NUEVO y diferente?",
        )
        return answer == QMessageBox.StandardButton.Yes

    def _create_building_inline(self) -> None:
        dialog = BuildingDialog(self)
        dialog.set_values()
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        values = dialog.values()
        name = str(values.get("name") or "").strip()
        if not name:
            QMessageBox.warning(self, "Falta información", "Escribe el nombre del edificio.")
            return
        exact = self._building_by_name.get(name.casefold())
        if exact is not None:
            QMessageBox.information(
                self, "Edificio existente",
                f'Ya existe “{exact["name"]}”. Atlas lo seleccionará y no creará un duplicado.',
            )
            self.fields["building"].setCurrentText(str(exact["name"]))
            return
        if not self._confirm_new_building_name(name):
            return
        try:
            self.database.save_building(values)
        except Exception as error:
            QMessageBox.critical(self, "No se pudo guardar", str(error))
            return
        self._reload_buildings(name)

    def accept(self) -> None:
        building_name = self.fields["building"].currentText().strip()
        if not self._confirm_new_building_name(building_name):
            return
        super().accept()

    def set_values(self, row=None):
        # Preserve the building catalog while clearing only editable values.
        for key, widget in self.fields.items():
            if isinstance(widget, QComboBox):
                widget.setCurrentText("")
            elif isinstance(widget, QTextEdit):
                widget.clear()
            else:
                widget.clear()

        if row is None:
            self.setWindowTitle("Nueva entrada")
            self._sync_inherited_address("")
            return

        self.setWindowTitle("Información de la dependencia")
        for key, widget in self.fields.items():
            value = str(row[key] or "")
            if isinstance(widget, QComboBox):
                widget.setCurrentText(value)
            elif isinstance(widget, QTextEdit):
                widget.setPlainText(value)
            else:
                widget.setText(value)
        self._sync_inherited_address(self.fields["building"].currentText())

    def values(self) -> dict[str, str]:
        result = {}
        for key, widget in self.fields.items():
            if isinstance(widget, QComboBox):
                result[key] = widget.currentText().strip()
            elif isinstance(widget, QTextEdit):
                result[key] = widget.toPlainText().strip()
            else:
                result[key] = widget.text().strip()
        return result



class ClickableFrame(QFrame):
    clicked = Signal()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class BuildingDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setModal(True)
        self.setMinimumSize(620, 620)
        self.resize(700, 700)
        self.setWindowTitle("Edificio")

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 18)
        root.setSpacing(14)

        title = QLabel("Información del edificio")
        title.setObjectName("dialogTitle")
        subtitle = QLabel(
            "Esta es la dirección única y autorizada del edificio. Todas las dependencias "
            "ubicadas aquí la heredan automáticamente."
        )
        subtitle.setObjectName("pageSubtitle")
        subtitle.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(subtitle)

        form = QFormLayout()
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(10)
        self.fields = {
            "name": line_edit("Nombre del edificio"),
            "street": line_edit("Calle o avenida"),
            "exterior_number": line_edit("Número exterior"),
            "colony": line_edit("Colonia"),
            "postal_code": line_edit("Código postal"),
            "city": line_edit("Ciudad"),
            "state": line_edit("Estado"),
            "country": line_edit("País"),
            "notes": notes_edit("Referencias, accesos u observaciones"),
        }
        self.fields["country"].setText("México")
        self.fields["notes"].setMinimumHeight(90)
        form.addRow("Nombre *", self.fields["name"])
        form.addRow("Calle", self.fields["street"])
        form.addRow("Número exterior", self.fields["exterior_number"])
        form.addRow("Colonia", self.fields["colony"])
        form.addRow("C.P.", self.fields["postal_code"])
        form.addRow("Ciudad", self.fields["city"])
        form.addRow("Estado", self.fields["state"])
        form.addRow("País", self.fields["country"])
        form.addRow("Notas", self.fields["notes"])
        root.addLayout(form)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save
        )
        save = self.buttons.button(QDialogButtonBox.StandardButton.Save)
        save.setText("Guardar edificio")
        save.setObjectName("primaryButton")
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        root.addWidget(self.buttons)

    def set_values(self, row=None):
        for widget in self.fields.values():
            widget.clear()
        self.fields["country"].setText("México")
        if row is None:
            self.setWindowTitle("Añadir edificio")
            return
        self.setWindowTitle("Editar edificio")
        for key, widget in self.fields.items():
            value = str(row[key] or "") if key in row.keys() else ""
            if isinstance(widget, QTextEdit):
                widget.setPlainText(value)
            else:
                widget.setText(value)

    def values(self) -> dict[str, str]:
        result = {}
        for key, widget in self.fields.items():
            result[key] = widget.toPlainText().strip() if isinstance(widget, QTextEdit) else widget.text().strip()
        return result


class EquipmentDialog(QDialog):
    """Create or edit an equipment record using the existing equipment table."""

    def __init__(self, database: Database, parent=None):
        super().__init__(parent)
        self.database = database
        self.setModal(True)
        self.setWindowTitle("Equipo")
        self.setMinimumSize(660, 620)
        self.resize(760, 700)

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 18)
        root.setSpacing(14)

        title = QLabel("Información del equipo")
        title.setObjectName("dialogTitle")
        subtitle = QLabel(
            "Los cambios se guardan en los campos existentes de inventario y "
            "se reflejan también en órdenes de servicio y contadores."
        )
        subtitle.setObjectName("pageSubtitle")
        subtitle.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(subtitle)

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(11)

        self.dependency = QComboBox()
        self.dependency.setMinimumContentsLength(36)
        for row in self.database.dependency_choices():
            label = f'{row["name"]} — {row["building"]}'
            if str(row["floor"] or "").strip():
                label += f' · {row["floor"]}'
            self.dependency.addItem(label, int(row["id"]))

        self.fields = {
            "equipment_type": line_edit("Ej. Impresora, escáner, multifuncional..."),
            "brand": line_edit("Marca"),
            "model": line_edit("Modelo"),
            "serial_number": line_edit("Número de serie"),
            "inventory_number": line_edit("Número de inventario"),
            "hostname": line_edit("Hostname"),
            "ip_address": line_edit("Ej. 192.168.1.25"),
            "assigned_user": line_edit("Nombre de quien utilizará el equipo (opcional)"),
            "notes": notes_edit("Observaciones"),
        }
        self.status = QComboBox()
        self.status.setEditable(True)
        self.status.addItems([
            "Activo", "En reparación", "Fuera de servicio", "Retirado", "Desconocido"
        ])
        self.fields["notes"].setMinimumHeight(90)
        self.fields["notes"].setMaximumHeight(150)

        form.addRow("Dependencia *", self.dependency)
        form.addRow("Descripción / tipo *", self.fields["equipment_type"])
        form.addRow("Marca", self.fields["brand"])
        form.addRow("Modelo", self.fields["model"])
        form.addRow("Número de serie", self.fields["serial_number"])
        form.addRow("No. de inventario", self.fields["inventory_number"])
        form.addRow("Hostname", self.fields["hostname"])
        form.addRow("IP", self.fields["ip_address"])
        form.addRow("Usuario del equipo", self.fields["assigned_user"])
        form.addRow("Estado", self.status)
        form.addRow("Observaciones", self.fields["notes"])
        root.addLayout(form)

        hint = QLabel(
            "No se permiten números de serie, inventario, hostname o direcciones IP repetidos."
        )
        hint.setObjectName("pageSubtitle")
        hint.setWordWrap(True)
        root.addWidget(hint)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Save
        )
        save = self.buttons.button(QDialogButtonBox.StandardButton.Save)
        save.setText("Guardar equipo")
        save.setObjectName("primaryButton")
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        root.addWidget(self.buttons)

    def set_values(self, row=None, dependency_id: int | None = None):
        for widget in self.fields.values():
            widget.clear()
        self.status.setCurrentText("Activo")

        selected_dependency = dependency_id
        if row is None:
            self.setWindowTitle("Añadir equipo")
        else:
            self.setWindowTitle("Modificar equipo")
            selected_dependency = int(row["dependency_id"])
            for key, widget in self.fields.items():
                value = str(row[key] or "")
                if isinstance(widget, QTextEdit):
                    widget.setPlainText(value)
                else:
                    widget.setText(value)
            self.status.setCurrentText(str(row["status"] or "Activo"))

        if selected_dependency is not None:
            index = self.dependency.findData(int(selected_dependency))
            if index >= 0:
                self.dependency.setCurrentIndex(index)

    def values(self) -> dict[str, object]:
        result: dict[str, object] = {
            "dependency_id": self.dependency.currentData(),
            "status": self.status.currentText().strip(),
        }
        for key, widget in self.fields.items():
            result[key] = (
                widget.toPlainText().strip()
                if isinstance(widget, QTextEdit)
                else widget.text().strip()
            )
        return result


class CounterDialog(QDialog):
    """Create, select, edit and delete counter readings for one equipment record."""

    def __init__(self, database: Database, equipment_id: int, parent=None):
        super().__init__(parent)
        self.database = database
        self.equipment_id = int(equipment_id)
        self.current_uid: str | None = None
        self._rows_by_uid: dict[str, object] = {}
        self.equipment = self.database.get_equipment_detailed(self.equipment_id)
        if self.equipment is None:
            raise ValueError("El equipo ya no existe.")

        self.setModal(True)
        self.setWindowTitle("Contador de impresiones")
        self.setMinimumSize(800, 670)
        self.resize(920, 760)

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 18)
        root.setSpacing(13)

        title = QLabel("Contador de impresiones")
        title.setObjectName("dialogTitle")
        root.addWidget(title)

        description = " ".join(
            part for part in (
                str(self.equipment["brand"] or "").strip(),
                str(self.equipment["model"] or "").strip(),
            ) if part
        ) or str(self.equipment["equipment_type"] or "Equipo")
        info = QLabel(
            f'<b>{description}</b><br>'
            f'Modelo: {self.equipment["model"] or "—"} · '
            f'Serie: {self.equipment["serial_number"] or "—"} · '
            f'Dependencia: {self.equipment["dependency_name"] or "—"}'
        )
        info.setObjectName("directoryPanel")
        info.setWordWrap(True)
        info.setContentsMargins(14, 12, 14, 12)
        root.addWidget(info)

        form = QGridLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(8)
        self.fields = {
            "reading_date": line_edit("AAAA-MM-DD"),
            "total_prints": line_edit("Total de impresiones"),
            "office_prints": line_edit("Impresiones tamaño carta"),
            "letter_prints": line_edit("Cálculo automático"),
            "duplex_sheets": line_edit("Hojas a ambas caras"),
            "jam_events": line_edit("Eventos de atasco"),
            "misfeed_events": line_edit("Páginas mal alimentadas"),
            "economode_prints": line_edit("Impresiones Economode"),
        }
        self.fields["letter_prints"].setReadOnly(True)
        labels = [
            ("Fecha *", "reading_date", 0, 0),
            ("Total de impresiones *", "total_prints", 0, 1),
            ("Impresiones tamaño carta", "office_prints", 1, 0),
            ("Impresiones tamaño Oficio", "letter_prints", 1, 1),
            ("Hojas a ambas caras", "duplex_sheets", 2, 0),
            ("Eventos de atasco", "jam_events", 2, 1),
            ("Eventos de páginas mal alimentadas", "misfeed_events", 3, 0),
            ("Impresiones Economode", "economode_prints", 3, 1),
        ]
        for label_text, key, row, column in labels:
            box = QVBoxLayout()
            label = QLabel(label_text)
            box.addWidget(label)
            box.addWidget(self.fields[key])
            form.addLayout(box, row, column)
        root.addLayout(form)

        form_actions = QHBoxLayout()
        self.new_button = QPushButton("Nuevo registro")
        self.new_button.setObjectName("softButton")
        self.save_button = QPushButton("Guardar registro")
        self.save_button.setObjectName("primaryButton")
        self.delete_button = QPushButton("Eliminar lectura")
        self.delete_button.setObjectName("dangerButton")
        form_actions.addWidget(self.new_button)
        form_actions.addStretch(1)
        form_actions.addWidget(self.delete_button)
        form_actions.addWidget(self.save_button)
        root.addLayout(form_actions)

        history_title = QLabel("Historial de lecturas — selecciona una fila para modificarla")
        history_title.setObjectName("equipmentName")
        root.addWidget(history_title)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels([
            "Fecha", "Total", "Equiv. A4/Carta", "Oficio", "Dúplex",
            "Atascos", "Mal alimentadas", "Economode"
        ])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        root.addWidget(self.table, 1)

        close_row = QHBoxLayout()
        close = QPushButton("Cerrar")
        close.clicked.connect(self.accept)
        close_row.addStretch(1)
        close_row.addWidget(close)
        root.addLayout(close_row)

        self.fields["total_prints"].textChanged.connect(self._update_office)
        self.fields["office_prints"].textChanged.connect(self._update_office)
        self.new_button.clicked.connect(self.new_record)
        self.save_button.clicked.connect(self.save_record)
        self.delete_button.clicked.connect(self.delete_record)
        self.table.itemSelectionChanged.connect(self.load_selected)
        self.refresh_history()
        self.new_record()

    @staticmethod
    def _number_text(value) -> str:
        if value is None or value == "":
            return ""
        number = float(value)
        return str(int(number)) if number.is_integer() else str(number)

    @staticmethod
    def _number(value: str, label: str, required: bool = False):
        text = str(value or "").strip().replace(",", "")
        if not text:
            if required:
                raise ValueError(f"Escribe {label}.")
            return None
        try:
            number = float(text)
        except ValueError as error:
            raise ValueError(f"{label} debe ser un número válido.") from error
        if number < 0:
            raise ValueError(f"{label} no puede ser negativo.")
        return int(number) if number.is_integer() else number

    def _update_office(self):
        try:
            total = self._number(self.fields["total_prints"].text(), "el total")
            equivalent = self._number(self.fields["office_prints"].text(), "el equivalente")
        except ValueError:
            self.fields["letter_prints"].clear()
            return
        if total is None or equivalent is None or float(equivalent) < float(total):
            self.fields["letter_prints"].clear()
            return
        self.fields["letter_prints"].clear()

    def new_record(self):
        self.current_uid = None
        self.table.clearSelection()
        for widget in self.fields.values():
            widget.clear()
        self.fields["reading_date"].setText(date.today().isoformat())
        self.save_button.setText("Guardar registro")
        self.delete_button.setEnabled(False)
        self.fields["total_prints"].setFocus()

    def refresh_history(self, select_uid: str | None = None):
        rows = self.database.list_equipment_counter_records(self.equipment_id)
        self._rows_by_uid = {str(row["record_uid"]): row for row in rows}
        self.table.blockSignals(True)
        self.table.setRowCount(len(rows))
        selected_row = None
        keys = [
            "reading_date", "total_prints", "office_prints", "letter_prints",
            "duplex_sheets", "jam_events", "misfeed_events", "economode_prints",
        ]
        for row_index, row in enumerate(rows):
            uid = str(row["record_uid"])
            for column, key in enumerate(keys):
                item = QTableWidgetItem(self._number_text(row[key]) if key != "reading_date" else str(row[key] or ""))
                item.setData(Qt.ItemDataRole.UserRole, uid)
                self.table.setItem(row_index, column, item)
            if select_uid and uid == select_uid:
                selected_row = row_index
        self.table.resizeColumnsToContents()
        self.table.blockSignals(False)
        if selected_row is not None:
            self.table.selectRow(selected_row)
            self.load_selected()

    def load_selected(self):
        selected = self.table.selectedItems()
        if not selected:
            return
        uid = str(selected[0].data(Qt.ItemDataRole.UserRole) or "")
        row = self._rows_by_uid.get(uid)
        if row is None:
            return
        self.current_uid = uid
        for key, widget in self.fields.items():
            widget.setText(self._number_text(row[key]) if key != "reading_date" else str(row[key] or ""))
        self.save_button.setText("Guardar cambios")
        self.delete_button.setEnabled(True)
        self._update_office()

    def values(self) -> dict[str, object]:
        reading_date = self.fields["reading_date"].text().strip()
        if not reading_date:
            raise ValueError("Escribe la fecha de la lectura.")
        total = self._number(
            self.fields["total_prints"].text(), "el total de impresiones", required=True
        )
        equivalent = self._number(
            self.fields["office_prints"].text(), "el total equivalente A4/Carta"
        )
        if equivalent is not None and float(equivalent) < float(total):
            raise ValueError(
                "El total equivalente A4/Carta no puede ser menor que el total de impresiones."
            )
        return {
            "reading_date": reading_date,
            "total_prints": total,
            "office_prints": None,
            "letter_prints": equivalent,
            "duplex_sheets": self._number(self.fields["duplex_sheets"].text(), "las hojas a ambas caras"),
            "jam_events": self._number(self.fields["jam_events"].text(), "los eventos de atasco"),
            "misfeed_events": self._number(self.fields["misfeed_events"].text(), "los eventos de páginas mal alimentadas"),
            "economode_prints": self._number(self.fields["economode_prints"].text(), "las impresiones Economode"),
        }

    def save_record(self):
        try:
            uid = self.database.save_equipment_counter(
                self.equipment_id, self.values(), self.current_uid
            )
        except Exception as error:
            QMessageBox.critical(self, "No se pudo guardar", str(error))
            return
        self.refresh_history(uid)
        QMessageBox.information(self, "Guardado", "La lectura se guardó correctamente.")

    def delete_record(self):
        if not self.current_uid:
            return
        answer = QMessageBox.question(
            self,
            "Eliminar lectura",
            "¿Eliminar la lectura seleccionada? Esta acción no puede deshacerse.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        if not self.database.delete_counter_record(self.current_uid):
            QMessageBox.warning(self, "No se encontró", "La lectura ya no existe.")
        self.refresh_history()
        self.new_record()


class DirectoryPage(QWidget):
    def __init__(self, database: Database, on_dependencies_changed=None):
        super().__init__()
        self.database = database
        self.on_dependencies_changed = on_dependencies_changed
        self.current_id: int | None = None
        self._rows_by_id = {}
        self._all_rows = []
        self._buildings = []
        self._buildings_by_id = {}
        self._equipment_by_dependency = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        hero = QFrame()
        hero.setObjectName("directoryHero")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(28, 24, 28, 24)
        title = QLabel("Directorio de Juzgados y Tribunales")
        title.setObjectName("directoryTitle")
        subtitle = QLabel(
            "Direcciones por edificio, dependencias editables y equipos con su último contador."
        )
        subtitle.setObjectName("directorySubtitle")
        subtitle.setWordWrap(True)
        hero_layout.addWidget(title)
        hero_layout.addWidget(subtitle)
        root.addWidget(hero)

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(24, 20, 24, 24)
        body_layout.setSpacing(14)
        root.addWidget(body, 1)

        toolbar = QFrame()
        toolbar.setObjectName("directoryPanel")
        toolbar_layout = QGridLayout(toolbar)
        toolbar_layout.setContentsMargins(16, 14, 16, 14)
        toolbar_layout.setHorizontalSpacing(12)
        toolbar_layout.setVerticalSpacing(6)
        toolbar_layout.addWidget(QLabel("Buscar"), 0, 0)
        toolbar_layout.addWidget(QLabel("Edificio"), 0, 1)
        toolbar_layout.addWidget(QLabel("Piso"), 0, 2)

        self.search = line_edit("Dependencia, CTA, equipo, serie, edificio, dirección...")
        self.building_filter = QComboBox()
        self.floor_filter = QComboBox()
        toolbar_layout.addWidget(self.search, 1, 0)
        toolbar_layout.addWidget(self.building_filter, 1, 1)
        toolbar_layout.addWidget(self.floor_filter, 1, 2)
        toolbar_layout.setColumnStretch(0, 1)
        toolbar_layout.setColumnMinimumWidth(1, 210)
        toolbar_layout.setColumnMinimumWidth(2, 180)
        body_layout.addWidget(toolbar)

        action_row = QHBoxLayout()
        self.add_button = QPushButton("＋ Nueva entrada")
        self.add_button.setObjectName("primaryButton")
        self.add_building_button = QPushButton("＋ Añadir edificio")
        self.add_building_button.setObjectName("softButton")
        self.refresh_button = QPushButton("Actualizar")
        self.print_button = QPushButton("Imprimir vista")
        action_row.addWidget(self.add_button)
        action_row.addWidget(self.add_building_button)
        action_row.addWidget(self.refresh_button)
        action_row.addWidget(self.print_button)
        action_row.addStretch(1)
        body_layout.addLayout(action_row)

        stats = QFrame()
        stats.setObjectName("directoryStats")
        stats_layout = QHBoxLayout(stats)
        stats_layout.setContentsMargins(16, 10, 16, 10)
        self.entry_count = QLabel("0 dependencias visibles")
        self.building_count = QLabel("0 edificios")
        self.equipment_count = QLabel("0 equipos")
        self.entry_count.setObjectName("statText")
        self.building_count.setObjectName("statText")
        self.equipment_count.setObjectName("statText")
        stats_layout.addWidget(self.entry_count)
        stats_layout.addSpacing(18)
        stats_layout.addWidget(self.building_count)
        stats_layout.addSpacing(18)
        stats_layout.addWidget(self.equipment_count)
        stats_layout.addStretch(1)
        saved = QLabel("Una sola base compartida por todos los módulos")
        saved.setObjectName("pageSubtitle")
        stats_layout.addWidget(saved)
        body_layout.addWidget(stats)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_content = QWidget()
        self.cards_layout = QVBoxLayout(self.scroll_content)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(14)
        self.cards_layout.addStretch(1)
        self.scroll.setWidget(self.scroll_content)
        body_layout.addWidget(self.scroll, 1)

        self.search.textChanged.connect(self.render)
        self.building_filter.currentTextChanged.connect(self.render)
        self.floor_filter.currentTextChanged.connect(self.render)
        self.add_button.clicked.connect(self.new_entry)
        self.add_building_button.clicked.connect(self.new_building)
        self.refresh_button.clicked.connect(self.refresh)
        self.print_button.clicked.connect(self.print_view)
        self.refresh()

    def clear_form(self):
        self.current_id = None

    def refresh(self):
        self._all_rows = self.database.list_dependencies("")
        self._rows_by_id = {int(row["id"]): row for row in self._all_rows}
        self._buildings = self.database.list_buildings()
        self._buildings_by_id = {int(row["id"]): row for row in self._buildings}
        self._equipment_by_dependency = self.database.directory_equipment()
        self._refresh_filters()
        self.render()

    def _refresh_filters(self):
        current_building = self.building_filter.currentText()
        current_floor = self.floor_filter.currentText()
        buildings = [str(row["name"] or "").strip() for row in self._buildings]
        floors = sorted(
            {str(row["floor"] or "").strip() for row in self._all_rows if row["floor"]},
            key=_floor_key,
        )
        self.building_filter.blockSignals(True)
        self.floor_filter.blockSignals(True)
        self.building_filter.clear()
        self.floor_filter.clear()
        self.building_filter.addItem("Todos los edificios")
        self.floor_filter.addItem("Todos los pisos")
        self.building_filter.addItems(buildings)
        self.floor_filter.addItems(floors)
        if current_building in buildings:
            self.building_filter.setCurrentText(current_building)
        if current_floor in floors:
            self.floor_filter.setCurrentText(current_floor)
        self.building_filter.blockSignals(False)
        self.floor_filter.blockSignals(False)

    def _row_search_text(self, row) -> str:
        parts = [str(row[key] or "") for key in (
            "name", "court", "tribunal", "office", "cta", "phone", "email",
            "building", "building_address", "floor", "street", "exterior_number",
            "colony", "postal_code", "city", "state", "notes",
        )]
        for equipment in self._equipment_by_dependency.get(int(row["id"]), []):
            parts.extend(str(equipment[key] or "") for key in (
                "equipment_type", "brand", "model", "serial_number",
                "inventory_number", "ip_address", "hostname", "status",
            ))
        return " ".join(parts).casefold()

    def _filtered_rows(self):
        query = self.search.text().strip().casefold()
        building = self.building_filter.currentText()
        floor = self.floor_filter.currentText()
        rows = []
        for row in self._all_rows:
            if query and query not in self._row_search_text(row):
                continue
            if building != "Todos los edificios" and str(row["building"] or "") != building:
                continue
            if floor != "Todos los pisos" and str(row["floor"] or "") != floor:
                continue
            rows.append(row)
        return rows

    def _clear_cards(self):
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def render(self):
        rows = self._filtered_rows()
        self._clear_cards()
        grouped = defaultdict(list)
        for row in rows:
            building_id = int(row["building_id"]) if row["building_id"] is not None else -1
            grouped[building_id].append(row)

        query = self.search.text().strip().casefold()
        selected_building = self.building_filter.currentText()
        selected_floor = self.floor_filter.currentText()
        visible_buildings = []
        for building in self._buildings:
            building_id = int(building["id"])
            name = str(building["name"] or "")
            if selected_building != "Todos los edificios" and name != selected_building:
                continue
            if selected_floor != "Todos los pisos" and building_id not in grouped:
                continue
            if query:
                building_text = f'{name} {building["address"] or ""}'.casefold()
                if building_id not in grouped and query not in building_text:
                    continue
            visible_buildings.append(building)

        visible_equipment = sum(
            len(self._equipment_by_dependency.get(int(row["id"]), []))
            for row in rows
        )
        self.entry_count.setText(f"{len(rows)} dependencias visibles")
        self.building_count.setText(f"{len(visible_buildings)} edificios")
        self.equipment_count.setText(f"{visible_equipment} equipos")
        if not visible_buildings:
            empty = QLabel("No se encontraron entradas con los filtros seleccionados.")
            empty.setObjectName("directoryEmpty")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setMinimumHeight(180)
            self.cards_layout.addWidget(empty)
            self.cards_layout.addStretch(1)
            return

        for building in visible_buildings:
            entries = sorted(
                grouped.get(int(building["id"]), []),
                key=lambda row: (
                    _floor_key(str(row["floor"] or "")),
                    str(row["name"] or "").casefold(),
                ),
            )
            self.cards_layout.addWidget(self._building_card(building, entries))
        self.cards_layout.addStretch(1)

    def _building_card(self, building, entries) -> QFrame:
        card = QFrame()
        card.setObjectName("buildingCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = ClickableFrame()
        header.setObjectName("buildingHeader")
        header.setCursor(Qt.CursorShape.PointingHandCursor)
        header.setToolTip("Haz clic para editar el nombre o la dirección del edificio")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 13, 16, 13)
        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        heading = QLabel(str(building["name"] or "Edificio sin nombre"))
        heading.setObjectName("buildingTitle")
        address = QLabel(str(building["address"] or "Dirección no especificada"))
        address.setObjectName("buildingAddress")
        address.setWordWrap(True)
        text_layout.addWidget(heading)
        text_layout.addWidget(address)
        header_layout.addLayout(text_layout, 1)
        edit_building = QPushButton("Editar edificio")
        edit_building.setObjectName("softButton")
        edit_building.setCursor(Qt.CursorShape.PointingHandCursor)
        building_id = int(building["id"])
        edit_building.clicked.connect(
            lambda checked=False, item_id=building_id: self.edit_building(item_id)
        )
        header_layout.addWidget(edit_building, alignment=Qt.AlignmentFlag.AlignTop)
        header.clicked.connect(lambda item_id=building_id: self.edit_building(item_id))
        layout.addWidget(header)

        if not entries:
            empty = QLabel("Este edificio todavía no tiene dependencias registradas.")
            empty.setObjectName("directoryEmpty")
            empty.setContentsMargins(16, 18, 16, 18)
            layout.addWidget(empty)
            return card

        column_header = QWidget()
        grid = QGridLayout(column_header)
        grid.setContentsMargins(14, 9, 14, 7)
        grid.setHorizontalSpacing(12)
        for column, text in enumerate(("PISO", "DEPENDENCIA", "CTA / ENCARGADO", "TIPO", "ACCIONES")):
            label = QLabel(text)
            label.setObjectName("directoryColumn")
            grid.addWidget(label, 0, column)
        grid.setColumnStretch(1, 4)
        grid.setColumnStretch(2, 2)
        layout.addWidget(column_header)

        for row in entries:
            layout.addWidget(self._dependency_block(row))
        return card

    def _dependency_block(self, row) -> QFrame:
        block = QFrame()
        block.setObjectName("directoryRow")
        block_layout = QVBoxLayout(block)
        block_layout.setContentsMargins(14, 10, 14, 10)
        block_layout.setSpacing(8)

        top = QWidget()
        row_layout = QGridLayout(top)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setHorizontalSpacing(12)
        floor = QLabel(str(row["floor"] or "Sin piso"))
        floor.setObjectName("floorBadge")
        floor.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        department = QPushButton(str(row["name"] or "Dependencia sin nombre"))
        department.setObjectName("departmentLink")
        department.setCursor(Qt.CursorShape.PointingHandCursor)
        dep_id = int(row["id"])
        department.clicked.connect(lambda checked=False, item_id=dep_id: self.edit_entry(item_id))
        cta = QLabel(str(row["cta"] or "—"))
        cta.setWordWrap(True)
        type_label = QLabel(_entry_type(row))
        edit_button = QPushButton("Editar")
        edit_button.setObjectName("softButton")
        delete_button = QPushButton("Eliminar")
        delete_button.setObjectName("dangerButton")
        edit_button.clicked.connect(lambda checked=False, item_id=dep_id: self.edit_entry(item_id))
        delete_button.clicked.connect(lambda checked=False, item_id=dep_id: self.delete_entry(item_id))
        actions = QWidget()
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(6)
        actions_layout.addWidget(edit_button)
        actions_layout.addWidget(delete_button)
        row_layout.addWidget(floor, 0, 0, alignment=Qt.AlignmentFlag.AlignTop)
        row_layout.addWidget(department, 0, 1, alignment=Qt.AlignmentFlag.AlignTop)
        row_layout.addWidget(cta, 0, 2, alignment=Qt.AlignmentFlag.AlignTop)
        row_layout.addWidget(type_label, 0, 3, alignment=Qt.AlignmentFlag.AlignTop)
        row_layout.addWidget(actions, 0, 4, alignment=Qt.AlignmentFlag.AlignTop)
        row_layout.setColumnStretch(1, 4)
        row_layout.setColumnStretch(2, 2)
        block_layout.addWidget(top)

        # Todos los campos aprobados del Directorio permanecen visibles en la
        # tarjeta. La ventana de edición modifica exactamente estos mismos
        # valores; no existe una segunda representación ni datos duplicados.
        details = QFrame()
        details.setObjectName("dependencyDetails")
        details_grid = QGridLayout(details)
        details_grid.setContentsMargins(12, 10, 12, 10)
        details_grid.setHorizontalSpacing(18)
        details_grid.setVerticalSpacing(7)

        def add_detail(label_text: str, value, row_index: int, column: int, span: int = 1):
            label = QLabel(label_text)
            label.setObjectName("directoryFieldLabel")
            text = QLabel(str(value or "—"))
            text.setObjectName("directoryFieldValue")
            text.setWordWrap(True)
            text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            box = QWidget()
            box_layout = QVBoxLayout(box)
            box_layout.setContentsMargins(0, 0, 0, 0)
            box_layout.setSpacing(2)
            box_layout.addWidget(label)
            box_layout.addWidget(text)
            details_grid.addWidget(box, row_index, column, 1, span)

        add_detail("Oficina / departamento", row["office"], 0, 0)
        add_detail("Teléfono", row["phone"], 0, 1)
        add_detail("Correo", row["email"], 0, 2)
        add_detail("Calle / avenida", row["street"], 1, 0, 2)
        add_detail("Número exterior", row["exterior_number"], 1, 2)
        add_detail("Colonia", row["colony"], 2, 0)
        add_detail("Código postal", row["postal_code"], 2, 1)
        add_detail("Ciudad", row["city"], 2, 2)
        add_detail("Estado", row["state"], 3, 0)
        add_detail("Notas", row["notes"], 3, 1, 2)
        details_grid.setColumnStretch(0, 1)
        details_grid.setColumnStretch(1, 1)
        details_grid.setColumnStretch(2, 1)

        info_toggle = QPushButton("▸ Ver información completa")
        info_toggle.setObjectName("equipmentToggle")
        info_toggle.setCheckable(True)
        info_toggle.setChecked(False)
        info_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        details.setVisible(False)
        info_toggle.toggled.connect(details.setVisible)
        info_toggle.toggled.connect(
            lambda open_, button=info_toggle: button.setText(
                f"{'▾' if open_ else '▸'} {'Ocultar información completa' if open_ else 'Ver información completa'}"
            )
        )
        block_layout.addWidget(info_toggle)
        block_layout.addWidget(details)

        equipment_rows = self._equipment_by_dependency.get(dep_id, [])
        with_counter = sum(1 for equipment in equipment_rows if equipment["latest_counter"] is not None)
        toggle = QPushButton()
        toggle.setObjectName("equipmentToggle")
        toggle.setCheckable(True)
        toggle.setChecked(False)
        toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        summary = f"{len(equipment_rows)} equipos · {with_counter} con contador"
        toggle.setText(f"▸ Equipos y contadores — {summary}")
        block_layout.addWidget(toggle)

        details = QFrame()
        details.setObjectName("equipmentPanel")
        details_layout = QVBoxLayout(details)
        details_layout.setContentsMargins(12, 8, 12, 8)
        details_layout.setSpacing(6)
        equipment_actions = QHBoxLayout()
        add_equipment = QPushButton("＋ Añadir equipo")
        add_equipment.setObjectName("softButton")
        add_equipment.clicked.connect(
            lambda checked=False, item_id=dep_id: self.new_equipment(item_id)
        )
        equipment_actions.addWidget(add_equipment)
        equipment_actions.addStretch(1)
        details_layout.addLayout(equipment_actions)
        if not equipment_rows:
            message = QLabel("Sin equipos registrados en esta dependencia.")
            message.setObjectName("pageSubtitle")
            details_layout.addWidget(message)
        else:
            for equipment in equipment_rows:
                details_layout.addWidget(self._equipment_row(equipment))
        details.setVisible(False)
        toggle.toggled.connect(details.setVisible)
        toggle.toggled.connect(
            lambda open_, button=toggle, text=summary: button.setText(
                f"{'▾' if open_ else '▸'} Equipos y contadores — {text}"
            )
        )
        block_layout.addWidget(details)
        return block

    def _equipment_row(self, equipment) -> QFrame:
        frame = QFrame()
        frame.setObjectName("equipmentItem")
        grid = QGridLayout(frame)
        grid.setContentsMargins(10, 8, 10, 8)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(6)
        equipment_id = int(equipment["id"])
        description = " ".join(
            part for part in (
                str(equipment["equipment_type"] or "").strip(),
                str(equipment["brand"] or "").strip(),
                str(equipment["model"] or "").strip(),
            ) if part
        ) or "Equipo sin descripción"
        name = QPushButton(description)
        name.setObjectName("departmentLink")
        name.setCursor(Qt.CursorShape.PointingHandCursor)
        name.clicked.connect(
            lambda checked=False, item_id=equipment_id: self.edit_equipment(item_id)
        )
        serial = QLabel(f'Serie: {equipment["serial_number"] or "Sin serie"}')
        serial.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        counter = equipment["latest_counter"]
        if counter is None:
            counter_text = "Sin contador registrado"
        else:
            number = float(counter)
            formatted = f"{int(number):,}" if number.is_integer() else f"{number:,.2f}"
            reading_date = str(equipment["latest_counter_date"] or "").strip()
            counter_text = f"Último contador: {formatted}" + (f" · {reading_date}" if reading_date else "")
        counter_button = QPushButton(counter_text)
        counter_button.setObjectName("equipmentToggle")
        counter_button.setCursor(Qt.CursorShape.PointingHandCursor)
        counter_button.clicked.connect(
            lambda checked=False, item_id=equipment_id: self.edit_counters(item_id)
        )
        status = QLabel(str(equipment["status"] or ""))
        modify = QPushButton("Modificar")
        modify.setObjectName("softButton")
        modify.clicked.connect(
            lambda checked=False, item_id=equipment_id: self.edit_equipment(item_id)
        )
        delete = QPushButton("Eliminar")
        delete.setObjectName("dangerButton")
        delete.clicked.connect(
            lambda checked=False, item_id=equipment_id: self.delete_equipment(item_id)
        )
        actions = QWidget()
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(6)
        actions_layout.addWidget(modify)
        actions_layout.addWidget(delete)

        grid.addWidget(name, 0, 0)
        grid.addWidget(serial, 0, 1)
        grid.addWidget(status, 0, 2)
        grid.addWidget(actions, 0, 3)
        grid.addWidget(counter_button, 1, 0, 1, 4)
        grid.setColumnStretch(0, 3)
        grid.setColumnStretch(1, 2)
        grid.setColumnStretch(2, 1)
        return frame

    def new_equipment(self, dependency_id: int):
        dialog = EquipmentDialog(self.database, self)
        dialog.set_values(dependency_id=dependency_id)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        values = dialog.values()
        if values["dependency_id"] is None:
            QMessageBox.warning(self, "Falta dependencia", "Selecciona una dependencia.")
            return
        if not str(values["equipment_type"] or "").strip():
            QMessageBox.warning(self, "Falta información", "Escribe la descripción o tipo del equipo.")
            return
        try:
            self.database.save_equipment(values)
        except Exception as error:
            QMessageBox.critical(self, "No se pudo guardar", str(error))
            return
        self.refresh()
        if self.on_dependencies_changed:
            self.on_dependencies_changed()

    def edit_equipment(self, equipment_id: int):
        row = self.database.get_equipment_detailed(equipment_id)
        if row is None:
            QMessageBox.warning(self, "Equipo no encontrado", "El equipo ya no está disponible.")
            self.refresh()
            return
        dialog = EquipmentDialog(self.database, self)
        dialog.set_values(row)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        values = dialog.values()
        if values["dependency_id"] is None:
            QMessageBox.warning(self, "Falta dependencia", "Selecciona una dependencia.")
            return
        if not str(values["equipment_type"] or "").strip():
            QMessageBox.warning(self, "Falta información", "Escribe la descripción o tipo del equipo.")
            return
        try:
            self.database.save_equipment(values, equipment_id)
        except Exception as error:
            QMessageBox.critical(self, "No se pudo guardar", str(error))
            return
        self.refresh()
        if self.on_dependencies_changed:
            self.on_dependencies_changed()

    def delete_equipment(self, equipment_id: int):
        row = self.database.get_equipment_detailed(equipment_id)
        description = "Equipo"
        if row is not None:
            description = " ".join(
                part for part in (
                    str(row["brand"] or "").strip(),
                    str(row["model"] or "").strip(),
                    str(row["serial_number"] or "").strip(),
                ) if part
            ) or str(row["equipment_type"] or "Equipo")
        answer = QMessageBox.question(
            self,
            "Eliminar equipo",
            f'¿Eliminar “{description}”?\n\nLas lecturas históricas conservarán sus datos, pero quedarán sin equipo asociado.',
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.database.delete_equipment(equipment_id)
        except Exception as error:
            QMessageBox.warning(self, "No se pudo eliminar", str(error))
            return
        self.refresh()
        if self.on_dependencies_changed:
            self.on_dependencies_changed()

    def edit_counters(self, equipment_id: int):
        try:
            dialog = CounterDialog(self.database, equipment_id, self)
        except Exception as error:
            QMessageBox.warning(self, "No se pudo abrir", str(error))
            return
        dialog.exec()
        self.refresh()

    def new_building(self):
        dialog = BuildingDialog(self)
        dialog.set_values()
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        values = dialog.values()
        if not self._confirm_similar_building(str(values.get("name") or "")):
            return
        try:
            self.database.save_building(values)
        except Exception as error:
            QMessageBox.critical(self, "No se pudo guardar", str(error))
            return
        self.refresh()
        if self.on_dependencies_changed:
            self.on_dependencies_changed()

    def edit_building(self, building_id: int):
        row = self._buildings_by_id.get(building_id)
        if row is None:
            self.refresh()
            row = self._buildings_by_id.get(building_id)
        if row is None:
            QMessageBox.warning(self, "Edificio no encontrado", "El edificio ya no está disponible.")
            return
        dialog = BuildingDialog(self)
        dialog.set_values(row)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        values = dialog.values()
        if not self._confirm_similar_building(str(values.get("name") or ""), building_id):
            return
        try:
            self.database.save_building(values, building_id)
        except Exception as error:
            QMessageBox.critical(self, "No se pudo guardar", str(error))
            return
        self.refresh()
        if self.on_dependencies_changed:
            self.on_dependencies_changed()

    def _confirm_similar_building(self, name: str, building_id: int | None = None) -> bool:
        matches = self.database.similar_buildings(name, building_id)
        if not matches:
            return True
        lines = [f"• {item['name']} ({item['score']:.0%} similar)" for item in matches[:5]]
        answer = QMessageBox.question(
            self, "Posible edificio duplicado",
            "Atlas encontró nombres muy similares:\n\n" + "\n".join(lines) +
            "\n\n¿Confirmas que deseas guardar un edificio diferente?",
        )
        return answer == QMessageBox.StandardButton.Yes

    def _confirm_similar_dependency(self, values: dict[str, object], dependency_id: int | None = None) -> bool:
        matches = self.database.similar_dependencies(
            str(values.get("building") or ""), str(values.get("name") or ""),
            floor=str(values.get("floor") or ""), exclude_id=dependency_id,
        )
        if not matches:
            return True
        lines = [
            f"• {item['name']} — piso {item['floor'] or 'sin especificar'} ({item['score']:.0%} similar)"
            for item in matches[:5]
        ]
        answer = QMessageBox.question(
            self, "Posible dependencia duplicada",
            "Atlas encontró dependencias muy similares en el mismo edificio:\n\n" + "\n".join(lines) +
            "\n\nNo se fusionará nada automáticamente. ¿Confirmas que esta es una dependencia distinta?",
        )
        return answer == QMessageBox.StandardButton.Yes

    def new_entry(self):
        dialog = DependencyDialog(self.database, self)
        dialog.set_values()
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        values = dialog.values()
        if not values["name"]:
            QMessageBox.warning(self, "Falta información", "Escribe el nombre de la dependencia.")
            return
        if not self._confirm_similar_dependency(values):
            return
        try:
            self.database.save_dependency(values)
        except Exception as error:
            QMessageBox.critical(self, "No se pudo guardar", str(error))
            return
        self.refresh()
        if self.on_dependencies_changed:
            self.on_dependencies_changed()

    def edit_entry(self, dependency_id: int):
        row = self._rows_by_id.get(dependency_id)
        if row is None:
            self.refresh()
            row = self._rows_by_id.get(dependency_id)
        if row is None:
            QMessageBox.warning(self, "Entrada no encontrada", "La dependencia ya no está disponible.")
            return
        dialog = DependencyDialog(self.database, self)
        dialog.set_values(row)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        values = dialog.values()
        if not values["name"]:
            QMessageBox.warning(self, "Falta información", "Escribe el nombre de la dependencia.")
            return
        if not self._confirm_similar_dependency(values, dependency_id):
            return
        try:
            self.database.save_dependency(values, dependency_id)
        except Exception as error:
            QMessageBox.critical(self, "No se pudo guardar", str(error))
            return
        self.refresh()
        if self.on_dependencies_changed:
            self.on_dependencies_changed()

    def delete_entry(self, dependency_id: int):
        row = self._rows_by_id.get(dependency_id)
        name = str(row["name"] or "esta dependencia") if row is not None else "esta dependencia"
        answer = QMessageBox.question(
            self, "Eliminar dependencia",
            f'¿Eliminar “{name}”?\n\nNo podrá eliminarse si tiene equipos registrados.',
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.database.delete_dependency(dependency_id)
        except Exception as error:
            QMessageBox.warning(self, "No se pudo eliminar", str(error))
            return
        self.refresh()
        if self.on_dependencies_changed:
            self.on_dependencies_changed()

    def print_view(self):
        QMessageBox.information(
            self, "Vista para impresión",
            "La vista conserva edificios, direcciones, dependencias y equipos. "
            "Los detalles de equipos permanecen colapsados hasta que se abren.",
        )
