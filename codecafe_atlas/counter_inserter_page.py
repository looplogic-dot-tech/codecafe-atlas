from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QSplitter, QTableWidget, QTableWidgetItem,
    QTextEdit, QVBoxLayout, QWidget, QHeaderView, QProgressBar, QListWidget,
    QAbstractItemView
)

from .counter_inserter_engine import (
    APP_NAME, STATUS_VALUE, AnalysisResult, AtlasError, TARGET_BY_KEY,
    analyze_multiple_files, apply_analysis, discrepancy_report_path, display_number,
)


class _TaskWorker(QObject):
    """Ejecuta una operación pesada sin bloquear la interfaz."""

    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, operation):
        super().__init__()
        self._operation = operation

    def run(self) -> None:
        try:
            result = self._operation()
        except Exception as exc:
            self.failed.emit(str(exc))
        else:
            self.finished.emit(result)


class CounterInserterPage(QWidget):
    """Inserta contadores en AK–AR únicamente mediante coincidencia exacta de serie."""

    def __init__(self):
        super().__init__()
        self.analysis: AnalysisResult | None = None
        self._task_thread: QThread | None = None
        self._task_worker: _TaskWorker | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 22)
        root.setSpacing(14)

        title = QLabel("Insertador inteligente de contadores")
        title.setObjectName("pageTitle")
        root.addWidget(title)
        subtitle = QLabel(
            "Actualiza exclusivamente equipos de Torreón, filas 821–1404, contadores en AK–AR "
            f'y la columna H a “{STATUS_VALUE}” solo cuando existe al menos un contador mayor a 0. '
            "No agrega columnas, no crea hojas y nunca modifica fórmulas."
        )
        subtitle.setObjectName("pageSubtitle")
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)

        panel = QFrame()
        panel.setObjectName("nativePanel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(16, 16, 16, 16)
        panel_layout.setSpacing(10)

        self.master_edit = QLineEdit()
        self.master_edit.setPlaceholderText("Hoja maestra XLSX u ODS")
        master_row = QHBoxLayout()
        master_row.addWidget(QLabel("Hoja maestra:"))
        master_row.addWidget(self.master_edit, 1)
        master_btn = QPushButton("Examinar…")
        master_btn.clicked.connect(self._select_master)
        master_row.addWidget(master_btn)
        panel_layout.addLayout(master_row)

        report_row = QHBoxLayout()
        report_row.addWidget(QLabel("Fuentes:"))
        self.report_list = QListWidget()
        self.report_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.report_list.setMinimumHeight(82)
        self.report_list.setToolTip("Reportes CSV, XLSX u ODS que se analizarán conjuntamente contra la hoja maestra.")
        report_row.addWidget(self.report_list, 1)
        report_buttons = QVBoxLayout()
        self.report_add_btn = QPushButton("Añadir fuentes…")
        self.report_add_btn.clicked.connect(self._select_reports)
        report_buttons.addWidget(self.report_add_btn)
        self.report_remove_btn = QPushButton("Eliminar seleccionadas")
        self.report_remove_btn.clicked.connect(self._remove_selected_reports)
        report_buttons.addWidget(self.report_remove_btn)
        self.report_clear_btn = QPushButton("Limpiar")
        self.report_clear_btn.clicked.connect(self._clear_reports)
        report_buttons.addWidget(self.report_clear_btn)
        report_buttons.addStretch(1)
        report_row.addLayout(report_buttons)
        panel_layout.addLayout(report_row)

        options = QHBoxLayout()
        self.overwrite_check = QCheckBox("Permitir reemplazar valores existentes en AK–AR y documentarlos como discrepancia")
        self.overwrite_check.toggled.connect(self._invalidate)
        options.addWidget(self.overwrite_check)
        options.addStretch(1)
        self.analyze_btn = QPushButton("Analizar y preparar vista previa")
        self.analyze_btn.setObjectName("primaryButton")
        self.analyze_btn.clicked.connect(self._analyze)
        options.addWidget(self.analyze_btn)
        panel_layout.addLayout(options)
        root.addWidget(panel)

        self.summary = QLabel("Sin análisis")
        self.summary.setObjectName("nativeSectionTitle")
        root.addWidget(self.summary)

        splitter = QSplitter(Qt.Orientation.Vertical)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels([
            "Número de serie", "Fuente(s)", "Fila reporte", "Fila maestra", "Estado", "Celdas", "Detalle"
        ])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._show_details)
        splitter.addWidget(self.table)

        self.detail = QTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setPlaceholderText("Aquí aparecerán el mapeo detectado y el detalle del equipo seleccionado.")
        splitter.addWidget(self.detail)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        root.addWidget(splitter, 1)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(8)
        self.progress.hide()
        root.addWidget(self.progress)

        footer = QHBoxLayout()
        self.status = QLabel("Seleccione la hoja maestra y uno o varios reportes fuente.")
        self.status.setWordWrap(True)
        footer.addWidget(self.status, 1)
        self.generate_btn = QPushButton("Generar copia actualizada")
        self.generate_btn.setObjectName("primaryButton")
        self.generate_btn.setEnabled(False)
        self.generate_btn.clicked.connect(self._generate)
        footer.addWidget(self.generate_btn)
        root.addLayout(footer)

        self.master_edit.textChanged.connect(self._invalidate)

    def _select_master(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar hoja maestra", "", "Hojas compatibles (*.xlsx *.ods)"
        )
        if path:
            self.master_edit.setText(path)

    def _select_reports(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Seleccionar reportes fuente",
            "",
            "Reportes compatibles (*.csv *.xlsx *.ods)",
        )
        if not paths:
            return
        existing = {self.report_list.item(i).text() for i in range(self.report_list.count())}
        added = False
        for path in paths:
            if path not in existing:
                self.report_list.addItem(path)
                existing.add(path)
                added = True
        if added:
            self._invalidate()

    def _remove_selected_reports(self) -> None:
        rows = sorted({self.report_list.row(item) for item in self.report_list.selectedItems()}, reverse=True)
        for row in rows:
            self.report_list.takeItem(row)
        if rows:
            self._invalidate()

    def _clear_reports(self) -> None:
        if self.report_list.count():
            self.report_list.clear()
            self._invalidate()

    def _report_paths(self) -> list[Path]:
        return [Path(self.report_list.item(i).text()) for i in range(self.report_list.count())]

    def _invalidate(self) -> None:
        self.analysis = None
        self.generate_btn.setEnabled(False)
        self.status.setText("Los archivos u opciones cambiaron. Ejecute nuevamente el análisis.")

    def _set_busy(self, busy: bool, message: str = "") -> None:
        self.progress.setVisible(busy)
        self.analyze_btn.setEnabled(not busy)
        self.generate_btn.setEnabled((not busy) and self.analysis is not None)
        self.master_edit.setEnabled(not busy)
        self.report_list.setEnabled(not busy)
        self.report_add_btn.setEnabled(not busy)
        self.report_remove_btn.setEnabled(not busy)
        self.report_clear_btn.setEnabled(not busy)
        self.overwrite_check.setEnabled(not busy)
        if message:
            self.status.setText(message)

    def _start_task(self, operation, on_success, failure_message: str) -> None:
        if self._task_thread is not None:
            return
        thread = QThread(self)
        worker = _TaskWorker(operation)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(on_success)
        worker.finished.connect(thread.quit)
        worker.failed.connect(lambda detail: self._task_failed(failure_message, detail))
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._task_finished)
        self._task_thread = thread
        self._task_worker = worker
        thread.start()

    def _task_failed(self, message: str, detail: str) -> None:
        QMessageBox.critical(self, APP_NAME, detail)
        self.status.setText(message)

    def _task_finished(self) -> None:
        self._task_thread = None
        self._task_worker = None
        self._set_busy(False)

    def _analyze(self) -> None:
        master = self.master_edit.text().strip()
        reports = self._report_paths()
        if not master or not reports:
            QMessageBox.warning(self, APP_NAME, "Seleccione la hoja maestra y al menos un reporte fuente.")
            return
        overwrite = self.overwrite_check.isChecked()
        self.analysis = None
        self.table.setRowCount(0)
        self.summary.setText("Analizando…")
        self.detail.setPlainText(
            "Procesando archivos. En libros grandes esta operación puede tardar varios minutos. "
            "La barra en movimiento confirma que CodeCafe Atlas continúa trabajando."
        )
        self._set_busy(True, "Analizando estructura, coincidencias y campos compatibles…")
        self._start_task(
            lambda: analyze_multiple_files(Path(master), reports, overwrite),
            self._analysis_completed,
            "El análisis no pudo completarse.",
        )

    def _analysis_completed(self, result: object) -> None:
        self.analysis = result if isinstance(result, AnalysisResult) else None
        if self.analysis is None:
            self.status.setText("El análisis devolvió un resultado inválido.")
            return
        self._populate()
        writable = self.analysis.counts().get("writable_cells", 0)
        if writable > 0:
            self.status.setText("Vista previa terminada. La hoja maestra no ha sido modificada.")
        else:
            self.status.setText(
                "El análisis terminó sin valores nuevos. Puede generar una copia verificada sin cambios."
            )

    def _populate(self) -> None:
        assert self.analysis is not None
        self.table.setRowCount(len(self.analysis.decisions))
        for row_index, decision in enumerate(self.analysis.decisions):
            writable_cells = [
                item.target_letter for item in decision.fields
                if item.action in {"escribir", "sobrescribir", "escribir_cero"}
            ]
            cells = ", ".join(writable_cells) or "—"
            values = [
                decision.serial_raw,
                decision.source_names or self.analysis.report_path.name,
                str(decision.report_row),
                str(decision.master_row or "—"),
                decision.status.replace("_", " "),
                cells,
                decision.details,
            ]
            for column, value in enumerate(values):
                self.table.setItem(row_index, column, QTableWidgetItem(value))

        counts = self.analysis.counts()
        source_count = self.report_list.count()
        self.summary.setText(
            f"{source_count} fuente(s) · {counts.get('report_rows', 0)} registros · "
            f"{counts.get('writable_equipment', 0)} equipos listos · "
            f"{counts.get('writable_cells', 0)} celdas · "
            f"{counts.get('zero_fill_cells', 0)} ceros · "
            f"{counts.get('conflict_cells', 0)} conflictos · "
            f"{counts.get('discrepancies', 0)} discrepancias"
        )
        lines = ["MAPEO DETECTADO (fuentes → hoja maestra):"]
        for key, source_col in self.analysis.mapping.fields.items():
            letter, _, label = TARGET_BY_KEY[key]
            lines.append(
                f"• Columna {source_col + 1}: “{self.analysis.mapping.source_headers[key]}” → {letter}: {label}"
            )
        if self.analysis.mapping.unmapped:
            lines.append(
                "\nSin campo compatible: "
                + ", ".join(TARGET_BY_KEY[key][0] for key in self.analysis.mapping.unmapped)
                + ". En equipos realmente actualizados, las celdas vacías se completarán con 0."
            )
        lines.extend([
            "",
            "REGLA ESTRICTA: solo coincidencia exacta de número de serie normalizado.",
            "Únicamente se escriben AK–AR. Las celdas realmente vacías se completan con 0 cuando existe al menos un contador válido.",
            "Toda discrepancia se documenta en un CSV adicional para revisión manual.",
        ])
        self.detail.setPlainText("\n".join(lines))

    def _show_details(self) -> None:
        if self.analysis is None:
            return
        row = self.table.currentRow()
        if row < 0 or row >= len(self.analysis.decisions):
            return
        decision = self.analysis.decisions[row]
        lines = [
            f"Serie: {decision.serial_raw}",
            f"Fuente(s): {decision.source_names or self.analysis.report_path.name}",
            f"Fila del reporte: {decision.report_row}",
            f"Fila maestra: {decision.master_row or 'No encontrada'}",
            f"Estado: {decision.status}",
            decision.details,
            "",
        ]
        for item in decision.fields:
            lines.extend([
                f"{item.target_letter} · {item.target_label}",
                f"  Fuente: {item.source_header} = {display_number(item.source_value) or 'sin dato'}",
                f"  Existente: {display_number(item.existing_value) or 'vacío'}",
                f"  Acción: {item.action}",
                "",
            ])
        self.detail.setPlainText("\n".join(lines))

    def _generate(self) -> None:
        if self.analysis is None:
            QMessageBox.warning(self, APP_NAME, "Primero ejecute el análisis.")
            return
        master = Path(self.analysis.master_path)
        extension = master.suffix.lower()
        default_name = master.stem + "_CONTADORES_JULIO_TORREON" + extension
        file_filter = "Excel (*.xlsx)" if extension == ".xlsx" else "OpenDocument (*.ods)"
        output, _ = QFileDialog.getSaveFileName(
            self, "Guardar copia actualizada", str(master.parent / default_name), file_filter
        )
        if not output:
            return
        output_path = Path(output)
        try:
            same_file = output_path.resolve() == master.resolve()
        except OSError:
            same_file = output_path.absolute() == master.absolute()
        if same_file:
            QMessageBox.warning(
                self,
                APP_NAME,
                "Seleccione un nombre o ubicación diferente. La hoja maestra original no puede reemplazarse.",
            )
            return

        writable = self.analysis.counts().get("writable_cells", 0)
        if writable > 0:
            confirmation_text = (
                "Se generará una copia nueva de la hoja maestra.\n\n"
                "Solo se escribirán contadores autorizados en AK–AR para equipos de Torreón "
                "con coincidencia exacta de número de serie. Las celdas vacías se completarán con 0. "
                "Si existen discrepancias, se generará un CSV adicional para revisión manual. "
                "El archivo original no será reemplazado.\n\n¿Continuar?"
            )
        else:
            confirmation_text = (
                "El análisis no encontró valores nuevos compatibles.\n\n"
                "Se generará una copia verificada sin cambios de contadores y el archivo original "
                "no será reemplazado.\n\n¿Continuar?"
            )
        confirm = QMessageBox.question(self, APP_NAME, confirmation_text)
        if confirm != QMessageBox.StandardButton.Yes:
            return
        analysis = self.analysis
        equipment = len(analysis.updates())
        self._set_busy(
            True,
            "Generando y verificando la copia. No cierre CodeCafe Atlas ni desconecte la unidad de destino…",
        )
        self._start_task(
            lambda: apply_analysis(analysis, output_path),
            lambda result: self._generation_completed(int(result), equipment, output),
            "No se generó ninguna copia.",
        )

    def _generation_completed(self, written: int, equipment: int, output: str) -> None:
        discrepancy_path = discrepancy_report_path(Path(output))
        discrepancy_text = f"\n\nReporte de discrepancias:\n{discrepancy_path}" if discrepancy_path.exists() else "\n\nNo se detectaron discrepancias."
        if written > 0:
            self.status.setText(f"Copia verificada: {equipment} equipos y {written} celdas insertadas.")
            result_text = (
                f"Proceso terminado.\n\nEquipos actualizados: {equipment}\n"
                f"Celdas insertadas: {written}\n\nArchivo:\n{output}" + discrepancy_text
            )
        else:
            self.status.setText("Copia verificada generada sin cambios de contadores.")
            result_text = (
                "Proceso terminado.\n\nEl análisis no encontró valores nuevos; "
                "se generó una copia verificada sin cambios.\n\n"
                f"Archivo:\n{output}" + discrepancy_text
            )
        QMessageBox.information(self, APP_NAME, result_text)
