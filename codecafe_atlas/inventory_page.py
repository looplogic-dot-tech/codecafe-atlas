from __future__ import annotations

from collections.abc import Callable
import ipaddress
import re
import unicodedata

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .database import Database
from .ui_helpers import line_edit, notes_edit, page_header, standard_actions


class InventoryPage(QWidget):
    def __init__(
        self,
        database: Database,
        on_equipment_changed: Callable[[], None] | None = None,
    ):
        super().__init__()
        self.database = database
        self.on_equipment_changed = on_equipment_changed
        self.current_id: int | None = None
        self._rows_by_id = {}
        self._sort_column: int | None = None
        self._sort_order = Qt.SortOrder.AscendingOrder

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 18, 22, 22)
        root.addWidget(page_header(
            "Inventario de equipos",
            "Cada equipo queda asociado a una dependencia del directorio."
        ))

        search_row = QHBoxLayout()
        self.search = line_edit(
            "Buscar serie, número de inventario, modelo, IP, hostname, dependencia o edificio"
        )
        refresh_button = QPushButton("Actualizar")
        duplicates_button = QPushButton("Revisar series duplicadas")
        self.total_label = QLabel("Total de equipos: 0")
        self.total_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.total_label.setMinimumWidth(145)
        search_row.addWidget(self.search, 1)
        search_row.addWidget(self.total_label)
        search_row.addWidget(duplicates_button)
        search_row.addWidget(refresh_button)
        root.addLayout(search_row)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter, 1)

        self.table = QTableWidget(0, 11)
        self.table.setHorizontalHeaderLabels([
            "#", "Equipo", "Marca", "Modelo", "Serie", "No. inventario", "IP", "Hostname",
            "Estado", "Dependencia", "Edificio / piso"
        ])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSortIndicatorShown(False)
        self.table.horizontalHeader().sectionClicked.connect(self._on_header_clicked)
        splitter.addWidget(self.table)

        form_panel = QWidget()
        form_layout = QVBoxLayout(form_panel)
        form_layout.setContentsMargins(16, 0, 0, 0)

        equipment_box = QGroupBox("Datos del equipo")
        equipment_form = QFormLayout(equipment_box)

        self.dependency = QComboBox()
        self.dependency.setMinimumContentsLength(28)
        self.fields = {
            "equipment_type": line_edit("Impresora, escáner, multifuncional..."),
            "brand": line_edit("Marca"),
            "model": line_edit("Modelo"),
            "serial_number": line_edit("Número de serie"),
            "inventory_number": line_edit("Número de inventario institucional"),
            "ip_address": line_edit("IP, si está disponible"),
            "hostname": line_edit("Hostname, si está disponible"),
        }
        self.status = QComboBox()
        self.status.setEditable(True)
        self.status.addItems([
            "Activo", "En reparación", "Fuera de servicio", "Retirado", "Desconocido"
        ])
        self.fields["notes"] = notes_edit("Observaciones")

        equipment_form.addRow("Dependencia *", self.dependency)
        equipment_form.addRow("Tipo de equipo", self.fields["equipment_type"])
        equipment_form.addRow("Marca", self.fields["brand"])
        equipment_form.addRow("Modelo", self.fields["model"])
        equipment_form.addRow("Número de serie", self.fields["serial_number"])
        equipment_form.addRow("No. de inventario", self.fields["inventory_number"])
        equipment_form.addRow("IP", self.fields["ip_address"])
        equipment_form.addRow("Hostname", self.fields["hostname"])
        equipment_form.addRow("Estado", self.status)

        actions, new_button, save_button, delete_button = standard_actions()
        form_layout.addWidget(equipment_box)
        form_layout.addWidget(QLabel("Observaciones"))
        form_layout.addWidget(self.fields["notes"])
        form_layout.addWidget(actions)
        form_layout.addStretch(1)

        splitter.addWidget(form_panel)
        splitter.setSizes([820, 410])

        self.search.textChanged.connect(self.refresh)
        refresh_button.clicked.connect(self.full_refresh)
        duplicates_button.clicked.connect(self.review_duplicates)
        self.table.itemSelectionChanged.connect(self.load_selected)
        new_button.clicked.connect(self.clear_form)
        save_button.clicked.connect(self.save)
        delete_button.clicked.connect(self.delete)

        self.full_refresh()

    def refresh_dependencies(self):
        current = self.dependency.currentData()
        self.dependency.clear()
        for row in self.database.dependency_choices():
            label = f'{row["building"]} · Piso {row["floor"]} · {row["name"]}'.strip(" ·")
            self.dependency.addItem(label, int(row["id"]))
        if current is not None:
            index = self.dependency.findData(current)
            if index >= 0:
                self.dependency.setCurrentIndex(index)

    def full_refresh(self):
        self.refresh_dependencies()
        self.refresh()

    @staticmethod
    def _natural_text_key(value):
        text = str(value or "").strip()
        folded = unicodedata.normalize("NFKD", text.casefold())
        folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
        # Every token has the same outer shape so keys remain comparable
        # even when one value starts with digits (e.g. 3355...) and another
        # starts with letters (e.g. VNB...).  v1.0.24.10 returned bare ints
        # and strings, which can raise TypeError during sorting.
        return tuple(
            (0, int(part)) if part.isdigit() else (1, part)
            for part in re.split(r"(\d+)", folded)
            if part != ""
        )

    @classmethod
    def _ip_key(cls, value):
        text = str(value or "").strip()
        try:
            address = ipaddress.ip_address(text)
            return (0, address.version, int(address))
        except ValueError:
            return (1, cls._natural_text_key(text))

    def _sort_value(self, row, column: int):
        if column == 0:
            return int(row["id"])
        if column == 1:
            return row["equipment_type"]
        if column == 2:
            return row["brand"]
        if column == 3:
            return row["model"]
        if column == 4:
            return row["serial_number"]
        if column == 5:
            return row["inventory_number"]
        if column == 6:
            return row["ip_address"]
        if column == 7:
            return row["hostname"]
        if column == 8:
            return row["status"]
        if column == 9:
            return row["dependency_name"]
        if column == 10:
            return f'{row["building"]} / {row["floor"]}'
        return ""

    def _sort_key(self, row, column: int):
        value = self._sort_value(row, column)
        if column == 0:
            return int(value)
        if column == 6:
            return self._ip_key(value)
        return self._natural_text_key(value)

    def _sorted_rows(self, rows):
        if self._sort_column is None:
            return list(rows)
        column = self._sort_column
        nonblank = []
        blank = []
        for row in rows:
            value = self._sort_value(row, column)
            if column != 0 and not str(value or "").strip():
                blank.append(row)
            else:
                nonblank.append(row)
        reverse = self._sort_order == Qt.SortOrder.DescendingOrder
        nonblank.sort(key=lambda row: self._sort_key(row, column), reverse=reverse)
        # Empty values remain at the bottom in both directions.
        return nonblank + blank

    def _on_header_clicked(self, column: int):
        if self._sort_column == column:
            self._sort_order = (
                Qt.SortOrder.DescendingOrder
                if self._sort_order == Qt.SortOrder.AscendingOrder
                else Qt.SortOrder.AscendingOrder
            )
        else:
            self._sort_column = column
            self._sort_order = Qt.SortOrder.AscendingOrder
        header = self.table.horizontalHeader()
        header.setSortIndicatorShown(True)
        header.setSortIndicator(column, self._sort_order)
        selected_id = self.current_id
        self.refresh()
        self.select_equipment(selected_id)

    def refresh(self):
        rows = self._sorted_rows(self.database.list_equipment(self.search.text()))
        self._rows_by_id = {int(row["id"]): row for row in rows}
        self.table.setRowCount(len(rows))
        self.total_label.setText(f"Total de equipos: {len(rows)}")
        for row_index, row in enumerate(rows):
            values = [
                row_index + 1,
                row["equipment_type"], row["brand"], row["model"], row["serial_number"],
                row["inventory_number"], row["ip_address"], row["hostname"], row["status"],
                row["dependency_name"], f'{row["building"]} / {row["floor"]}',
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value or ""))
                item.setData(Qt.ItemDataRole.UserRole, int(row["id"]))
                if column == 0:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row_index, column, item)
        self.table.resizeColumnsToContents()
        self.table.setColumnWidth(0, 54)

    def load_selected(self):
        selected = self.table.selectedItems()
        if not selected:
            return
        equipment_id = int(selected[0].data(Qt.ItemDataRole.UserRole))
        row = self._rows_by_id.get(equipment_id)
        if row is None:
            return
        self.current_id = equipment_id
        dependency_index = self.dependency.findData(int(row["dependency_id"]))
        if dependency_index >= 0:
            self.dependency.setCurrentIndex(dependency_index)
        for key, widget in self.fields.items():
            value = str(row[key] or "")
            widget.setPlainText(value) if hasattr(widget, "setPlainText") else widget.setText(value)
        self.status.setCurrentText(str(row["status"] or ""))

    def clear_form(self):
        self.current_id = None
        self.table.clearSelection()
        for widget in self.fields.values():
            widget.clear()
        self.status.setCurrentText("Activo")
        if self.dependency.count():
            self.dependency.setCurrentIndex(0)
        self.fields["equipment_type"].setFocus()

    def values(self):
        data = {
            "dependency_id": self.dependency.currentData(),
            "status": self.status.currentText().strip(),
        }
        for key, widget in self.fields.items():
            data[key] = (
                widget.toPlainText().strip()
                if hasattr(widget, "toPlainText")
                else widget.text().strip()
            )
        return data

    def save(self):
        values = self.values()
        if values["dependency_id"] is None:
            QMessageBox.warning(
                self,
                "Falta dependencia",
                "Primero registra una dependencia en el directorio."
            )
            return
        try:
            self.current_id = self.database.save_equipment(values, self.current_id)
        except Exception as error:
            QMessageBox.critical(self, "No se pudo guardar", str(error))
            return
        saved_id = self.current_id
        self.refresh()
        self.select_equipment(saved_id)
        if self.on_equipment_changed:
            self.on_equipment_changed()
        QMessageBox.information(self, "Guardado", "El equipo se guardó y verificó correctamente.")


    def select_equipment(self, equipment_id: int | None):
        if equipment_id is None:
            return
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and int(item.data(Qt.ItemDataRole.UserRole)) == int(equipment_id):
                self.table.selectRow(row)
                self.table.scrollToItem(item)
                return

    def review_duplicates(self):
        groups = self.database.equipment_duplicate_groups()
        if not groups:
            QMessageBox.information(self, "Series duplicadas", "No se encontraron números de serie duplicados.")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Revisar y fusionar series duplicadas")
        dialog.resize(1050, 560)
        layout = QVBoxLayout(dialog)
        info = QLabel("Selecciona el registro que debe conservarse. Atlas trasladará su historial y órdenes de servicio, completará campos vacíos con datos de los otros registros y eliminará únicamente los duplicados del mismo grupo.")
        info.setWordWrap(True)
        layout.addWidget(info)
        progress_label = QLabel()
        layout.addWidget(progress_label)
        group_combo = QComboBox()
        layout.addWidget(group_combo)
        table = QTableWidget(0, 9)
        table.setHorizontalHeaderLabels(["ID","Serie","Tipo","Marca","Modelo","Inventario","IP","Dependencia","Edificio"])
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(table, 1)
        merge_button = QPushButton("Conservar seleccionado y eliminar los demás")
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.addButton(merge_button, QDialogButtonBox.ButtonRole.ActionRole)
        layout.addWidget(buttons)

        state = {"groups": groups}

        def rebuild_combo(preferred_index=0):
            current_groups = state["groups"]
            group_combo.blockSignals(True)
            group_combo.clear()
            for index, group in enumerate(current_groups):
                serials = sorted({str(r["serial_number"] or "") for r in group["records"]})
                group_combo.addItem(f"{', '.join(serials)} — {len(group['records'])} registros", index)
            if current_groups:
                group_combo.setCurrentIndex(min(preferred_index, len(current_groups)-1))
                progress_label.setText(f"Grupos duplicados pendientes: {len(current_groups)}")
            else:
                progress_label.setText("No quedan series duplicadas.")
            group_combo.blockSignals(False)

        def load_group():
            if not state["groups"] or group_combo.currentIndex() < 0:
                table.setRowCount(0)
                return
            records = state["groups"][int(group_combo.currentData())]["records"]
            table.setRowCount(len(records))
            for i, row in enumerate(records):
                values = [row["id"],row["serial_number"],row["equipment_type"],row["brand"],row["model"],row["inventory_number"],row["ip_address"],row["dependency_name"],row["building_name"]]
                for j, value in enumerate(values):
                    item = QTableWidgetItem(str(value or ""))
                    item.setData(Qt.ItemDataRole.UserRole, int(row["id"]))
                    table.setItem(i,j,item)
            table.resizeColumnsToContents()
            if records:
                table.selectRow(0)

        def merge_selected():
            selected = table.selectedItems()
            if not selected:
                QMessageBox.warning(dialog, "Sin selección", "Selecciona el registro que deseas conservar.")
                return
            current_index = group_combo.currentIndex()
            group = state["groups"][int(group_combo.currentData())]
            keep_id = int(selected[0].data(Qt.ItemDataRole.UserRole))
            remove_ids = sorted({int(r["id"]) for r in group["records"] if int(r["id"]) != keep_id})
            if not remove_ids:
                QMessageBox.warning(dialog, "Grupo inválido", "Este grupo no contiene dos equipos distintos. Atlas actualizará la lista para evitar un falso duplicado.")
                state["groups"] = self.database.equipment_duplicate_groups()
                rebuild_combo(current_index)
                load_group()
                return
            answer = QMessageBox.question(dialog, "Confirmar fusión", f"Se conservará el equipo ID {keep_id} y se eliminarán {len(remove_ids)} registros duplicados. El historial relacionado será trasladado. ¿Continuar?")
            if answer != QMessageBox.StandardButton.Yes:
                return
            try:
                self.database.merge_duplicate_equipment(keep_id, remove_ids)
            except Exception as error:
                QMessageBox.critical(dialog, "No se pudo fusionar", str(error))
                return

            self.full_refresh()
            self.select_equipment(keep_id)
            if self.on_equipment_changed:
                self.on_equipment_changed()

            # Re-read the database after every merge. The dialog remains open and
            # advances to the next pending group; it closes only when none remain.
            state["groups"] = self.database.equipment_duplicate_groups()
            if not state["groups"]:
                QMessageBox.information(dialog, "Revisión completada", "Ya no quedan números de serie duplicados.")
                dialog.accept()
                return
            rebuild_combo(min(current_index, len(state["groups"])-1))
            load_group()

        group_combo.currentIndexChanged.connect(load_group)
        merge_button.clicked.connect(merge_selected)
        buttons.rejected.connect(dialog.reject)
        rebuild_combo(0)
        load_group()
        dialog.exec()

    def delete(self):
        if self.current_id is None:
            QMessageBox.information(self, "Sin selección", "Selecciona un equipo para eliminar.")
            return
        answer = QMessageBox.question(
            self,
            "Eliminar equipo",
            "¿Eliminar el equipo seleccionado? Esta acción no puede deshacerse.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.database.delete_equipment(self.current_id)
        except Exception as error:
            QMessageBox.warning(self, "No se pudo eliminar", str(error))
            return
        self.clear_form()
        self.refresh()
        if self.on_equipment_changed:
            self.on_equipment_changed()
