from __future__ import annotations

import csv
import json
import shutil
import sqlite3
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .database import Database
from .sync_engine import SyncEngine, SyncItem, SYNC_TABLES, TABLE_LABELS

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout,
    QWidget, QHeaderView, QComboBox,
)



class SyncComparePage(QWidget):
    def __init__(self, database):
        super().__init__()
        self.database = database
        self.results: list[SyncItem] = []
        self.summary: dict[str, dict[str, int]] = {}
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(14)

        title = QLabel("Homologación de bases de datos")
        title.setObjectName("pageTitle")
        subtitle = QLabel(
            "Analiza, resuelve y homologa una base externa con la base local mediante respaldo y transacción segura."
        )
        subtitle.setWordWrap(True)
        subtitle.setObjectName("pageSubtitle")
        root.addWidget(title)
        root.addWidget(subtitle)

        panel = QFrame()
        panel.setObjectName("nativePanel")
        layout = QVBoxLayout(panel)
        local_row = QHBoxLayout()
        local_row.addWidget(QLabel("Base local:"))
        self.local_path = QLineEdit(str(self.database.path))
        self.local_path.setReadOnly(True)
        local_row.addWidget(self.local_path, 1)
        layout.addLayout(local_row)

        external_row = QHBoxLayout()
        external_row.addWidget(QLabel("Base externa:"))
        self.external_path = QLineEdit()
        self.external_path.setPlaceholderText("Selecciona el archivo .db de otra computadora")
        browse = QPushButton("Examinar…")
        browse.clicked.connect(self._browse)
        external_row.addWidget(self.external_path, 1)
        external_row.addWidget(browse)
        layout.addLayout(external_row)

        actions = QHBoxLayout()
        compare = QPushButton("Analizar homologación")
        compare.setObjectName("primaryButton")
        compare.clicked.connect(self._compare)
        self.homologate_button = QPushButton("Homologar base local")
        self.homologate_button.setEnabled(False)
        self.homologate_button.clicked.connect(self._homologate)
        self.export_button = QPushButton("Exportar reporte CSV")
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self._export)
        actions.addWidget(compare)
        actions.addWidget(self.export_button)
        actions.addWidget(self.homologate_button)
        actions.addStretch(1)
        layout.addLayout(actions)
        root.addWidget(panel)

        self.summary_label = QLabel("Selecciona una base externa para iniciar el análisis.")
        self.summary_label.setObjectName("nativeNotice")
        self.summary_label.setWordWrap(True)
        root.addWidget(self.summary_label)

        self.tabs = QTabWidget()
        self.tables: dict[str, QTableWidget] = {}
        for status in ("Resumen", "Nuevos", "Coincidentes", "Conflictos", "Posibles duplicados", "Solo local"):
            table = QTableWidget(0, 5 if status != "Resumen" else 6)
            if status == "Resumen":
                table.setHorizontalHeaderLabels(["Entidad", "Nuevos", "Coincidentes", "Conflictos", "Duplicados", "Solo local"])
            else:
                table.setHorizontalHeaderLabels(["Entidad", "Identificador", "UUID", "Detalle", "Decisión"])
            table.setAlternatingRowColors(True)
            table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
            table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            self.tabs.addTab(table, status)
            self.tables[status] = table
        root.addWidget(self.tabs, 1)

    def _browse(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar base externa", "", "Bases SQLite (*.db *.sqlite *.sqlite3);;Todos los archivos (*)"
        )
        if selected:
            self.external_path.setText(selected)

    def _compare(self) -> None:
        path = self.external_path.text().strip()
        if not path:
            QMessageBox.warning(self, "Base externa", "Selecciona una base externa.")
            return
        try:
            previous = getattr(self, "plan", None)
            if previous is not None:
                previous.close()
            self.plan = SyncEngine(self.database.path, Path(path)).analyze()
            self.results, self.summary = self.plan.items, self.plan.summary
        except Exception as exc:
            self.summary_label.setProperty("error", True)
            self.summary_label.style().unpolish(self.summary_label)
            self.summary_label.style().polish(self.summary_label)
            self.summary_label.setText(str(exc))
            QMessageBox.critical(self, "No se pudo comparar", str(exc))
            return
        self.summary_label.setProperty("error", False)
        self.summary_label.style().unpolish(self.summary_label)
        self.summary_label.style().polish(self.summary_label)
        totals = {key: sum(item[key] for item in self.summary.values()) for key in ("nuevos", "coincidentes", "conflictos", "duplicados", "solo_local")}
        compatibility = (" " + self.plan.compatibility_note) if self.plan.compatibility_note else ""
        self.summary_label.setText(
            f"Análisis terminado: {totals['nuevos']} nuevos, {totals['coincidentes']} coincidentes, "
            f"{totals['conflictos']} conflictos, {totals['duplicados']} posibles duplicados y "
            f"{totals['solo_local']} registros solo locales. Revisa las decisiones antes de homologar.{compatibility}"
        )
        self._populate()
        self.export_button.setEnabled(True)
        self.homologate_button.setEnabled(True)

    def _populate(self) -> None:
        summary_table = self.tables["Resumen"]
        summary_table.setRowCount(0)
        for table_name in SYNC_TABLES:
            counts = self.summary.get(table_name, {})
            row = summary_table.rowCount()
            summary_table.insertRow(row)
            values = [TABLE_LABELS[table_name], counts.get("nuevos", 0), counts.get("coincidentes", 0), counts.get("conflictos", 0), counts.get("duplicados", 0), counts.get("solo_local", 0)]
            for col, value in enumerate(values):
                summary_table.setItem(row, col, QTableWidgetItem(str(value)))

        mapping = {
            "Nuevo externo": "Nuevos", "Coincidente": "Coincidentes", "Conflicto": "Conflictos",
            "Posible duplicado": "Posibles duplicados", "Solo local": "Solo local",
        }
        for name in mapping.values():
            self.tables[name].setRowCount(0)
        for item in self.results:
            target = self.tables[mapping[item.status]]
            row = target.rowCount()
            target.insertRow(row)
            values = [TABLE_LABELS[item.table], item.identifier, item.record_uuid, item.detail]
            for col, value in enumerate(values):
                target.setItem(row, col, QTableWidgetItem(str(value)))
            combo = QComboBox()
            if item.status == "Nuevo externo": options = ["Importar", "Ignorar"]
            elif item.status == "Conflicto": options = ["Conservar local", "Usar externo"]
            elif item.status == "Posible duplicado": options = ["Conservar local", "Usar externo"]
            else: options = [item.decision]
            combo.addItems(options); combo.setCurrentText(item.decision)
            combo.currentTextChanged.connect(lambda value, obj=item: setattr(obj, "decision", value))
            target.setCellWidget(row, 4, combo)

    def _homologate(self) -> None:
        if not getattr(self, "plan", None):
            return
        answer = QMessageBox.question(self, "Confirmar homologación", "Se creará un respaldo y se modificará la base local según las decisiones mostradas. ¿Continuar?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            data, json_path, csv_path = SyncEngine(self.database.path, Path(self.external_path.text())).apply(self.plan)
            self.homologate_button.setEnabled(False)
            QMessageBox.information(self, "Homologación terminada", f"Proceso completado.\n\nInsertados: {data['resultados']['insertados']}\nActualizados: {data['resultados']['actualizados']}\nOmitidos: {data['resultados']['omitidos']}\n\nRespaldo: {data['respaldo']}\nInforme JSON: {json_path}\nInforme CSV: {csv_path}")
            self.summary_label.setText("Homologación completada y validada. Se recomienda reiniciar CodeCafe Atlas para recargar todos los módulos.")
        except Exception as exc:
            QMessageBox.critical(self, "Homologación cancelada", f"No se aplicaron cambios permanentes.\n\n{exc}")

    def _export(self) -> None:
        selected, _ = QFileDialog.getSaveFileName(
            self, "Guardar reporte de homologación", "reporte_homologacion.csv", "CSV (*.csv)"
        )
        if not selected:
            return
        try:
            with open(selected, "w", newline="", encoding="utf-8-sig") as handle:
                writer = csv.writer(handle)
                writer.writerow(["Entidad", "Estado", "Identificador", "UUID", "Detalle"])
                for item in self.results:
                    writer.writerow([TABLE_LABELS[item.table], item.status, item.identifier, item.record_uuid, item.detail])
            QMessageBox.information(self, "Reporte exportado", f"Reporte guardado en:\n{selected}")
        except OSError as exc:
            QMessageBox.critical(self, "No se pudo exportar", str(exc))
