from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QSettings, QThread, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QSplitter, QTableWidget, QTableWidgetItem,
    QTextEdit, QVBoxLayout, QWidget, QHeaderView, QProgressBar, QListWidget,
    QAbstractItemView, QComboBox, QInputDialog
)

from .counter_inserter_engine import (
    APP_NAME, AnalysisResult, TARGET_BY_KEY,
    analyze_multiple_files, apply_analysis, configure_target_columns,
    col_letter, discrepancy_report_path, display_number, master_sheet_names,
    normalize_serial, read_atlas_counter_database, suggest_master_sheet, target_range_label,
)
from .paths import database_path


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
    """Inserta contadores en un bloque mensual seleccionable de ocho columnas."""

    def __init__(self):
        super().__init__()
        self.analysis: AnalysisResult | None = None
        self._settings = QSettings("CodeCafe.io", "CodeCafe Atlas")
        self._task_thread: QThread | None = None
        self._task_worker: _TaskWorker | None = None
        self._serial_overrides: dict[str, str] = {}
        self._populating_table = False
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 22)
        root.setSpacing(14)

        title = QLabel("Insertador inteligente de contadores")
        title.setObjectName("pageTitle")
        root.addWidget(title)
        subtitle = QLabel(
            "Busca cada equipo de Torreón por número de serie exacto y actualiza la pestaña, "
            "las filas y las columnas de contador que detecte o que usted seleccione. "
            "No agrega columnas, no crea hojas y nunca modifica fórmulas."
        )
        subtitle.setObjectName("pageSubtitle")
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)

        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_splitter.setChildrenCollapsible(False)
        main_splitter.setHandleWidth(8)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 6, 0)
        left_layout.setSpacing(0)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(6, 0, 0, 0)
        right_layout.setSpacing(10)

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

        sheet_row = QHBoxLayout()
        sheet_row.addWidget(QLabel("Pestaña destino:"))
        self.sheet_combo = QComboBox()
        self.sheet_combo.setEditable(True)
        self.sheet_combo.setToolTip("Pestaña de la hoja maestra donde se buscarán los números de serie.")
        self.sheet_combo.currentTextChanged.connect(self._invalidate)
        sheet_row.addWidget(self.sheet_combo, 1)
        panel_layout.addLayout(sheet_row)

        columns_row = QHBoxLayout()
        columns_row.addWidget(QLabel("Mapeo destino:"))
        saved_target = self._settings.value("counter_inserter/target_spec", "AUTO", type=str)
        self.target_range_edit = QLineEdit(saved_target or "AUTO")
        self.target_range_edit.setPlaceholderText("AUTO o R,S,V,W")
        self.target_range_edit.setToolTip(
            "AUTO detecta cada encabezado. Manualmente indique únicamente las columnas que existan, "
            "en orden: impresiones, equivalentes, dúplex, atascos, escaneos, copias, color y "
            "digitalizaciones. Por ejemplo R,S,V,W."
        )
        self.target_range_edit.setMaximumWidth(240)
        columns_row.addWidget(self.target_range_edit)
        columns_row.addStretch(1)
        panel_layout.addLayout(columns_row)

        serial_row = QHBoxLayout()
        serial_row.addWidget(QLabel("Serie en hoja maestra:"))
        saved_serial = self._settings.value("counter_inserter/master_serial_col", "B", type=str)
        self.master_serial_edit = QLineEdit(saved_serial or "B")
        self.master_serial_edit.setPlaceholderText("AUTO o B")
        self.master_serial_edit.setToolTip(
            "Columna que contiene los números de serie en la pestaña destino. "
            "El reporte fuente lo genera Atlas y se interpreta automáticamente."
        )
        self.master_serial_edit.setMaximumWidth(120)
        serial_row.addWidget(self.master_serial_edit)
        serial_row.addStretch(1)
        panel_layout.addLayout(serial_row)

        source_mode_row = QHBoxLayout()
        source_mode_row.addWidget(QLabel("Origen de contadores:"))
        self.database_source_check = QCheckBox("Base de datos de Atlas")
        self.database_source_check.setChecked(
            self._settings.value("counter_inserter/use_database", True, type=bool)
        )
        self.database_source_check.setToolTip(
            "Incluye la lectura más reciente guardada para cada número de serie. "
            "La base solo se modifica si se autoriza importar una IP faltante."
        )
        self.database_source_check.toggled.connect(self._database_source_changed)
        source_mode_row.addWidget(self.database_source_check)
        source_mode_row.addStretch(1)
        panel_layout.addLayout(source_mode_row)

        location_options = QVBoxLayout()
        location_options.setSpacing(6)
        self.sync_location_check = QCheckBox(
            "Completar Ubicación de Equipo desde la dependencia de Atlas"
        )
        self.sync_location_check.setChecked(
            self.database_source_check.isChecked()
            and self._settings.value("counter_inserter/sync_location", False, type=bool)
        )
        self.sync_location_check.setEnabled(self.database_source_check.isChecked())
        self.sync_location_check.setToolTip(
            "Detecta el encabezado Ubicación de Equipo —actualmente P— y llena únicamente las celdas vacías."
        )
        self.sync_location_check.toggled.connect(self._location_option_changed)
        location_options.addWidget(self.sync_location_check)
        self.replace_location_check = QCheckBox(
            "Reemplazar también ubicaciones existentes"
        )
        self.replace_location_check.setChecked(
            self._settings.value("counter_inserter/replace_location", False, type=bool)
        )
        self.replace_location_check.setEnabled(
            self.database_source_check.isChecked() and self.sync_location_check.isChecked()
        )
        self.replace_location_check.setToolTip(
            "Sustituye el valor de la hoja maestra cuando difiere de la dependencia registrada en Atlas."
        )
        self.replace_location_check.toggled.connect(self._location_option_changed)
        location_options.addWidget(self.replace_location_check)
        self.sync_auxiliary_check = QCheckBox(
            "Completar fecha del contador, piso e IP desde Atlas"
        )
        self.sync_auxiliary_check.setChecked(
            self.database_source_check.isChecked()
            and self._settings.value("counter_inserter/sync_auxiliary", True, type=bool)
        )
        self.sync_auxiliary_check.setEnabled(self.database_source_check.isChecked())
        self.sync_auxiliary_check.setToolTip(
            "Detecta los encabezados reales y completa únicamente campos vacíos; no reemplaza valores existentes."
        )
        self.sync_auxiliary_check.toggled.connect(self._auxiliary_option_changed)
        location_options.addWidget(self.sync_auxiliary_check)
        self.import_missing_ip_check = QCheckBox(
            "Importar a Atlas las IP faltantes encontradas en la hoja maestra"
        )
        self.import_missing_ip_check.setChecked(False)
        self.import_missing_ip_check.setEnabled(self.database_source_check.isChecked())
        self.import_missing_ip_check.setToolTip(
            "Solo llena IP vacías en Atlas. Nunca reemplaza una IP existente y crea un respaldo antes de escribir."
        )
        self.import_missing_ip_check.toggled.connect(self._auxiliary_option_changed)
        location_options.addWidget(self.import_missing_ip_check)
        panel_layout.addLayout(location_options)

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

        new_rows_options = QVBoxLayout()
        new_rows_options.setSpacing(6)
        self.create_missing_check = QCheckBox(
            "Añadir series faltantes a la copia"
        )
        self.create_missing_check.setChecked(
            self._settings.value("counter_inserter/create_missing_rows", True, type=bool)
        )
        self.create_missing_check.setToolTip(
            "Crea filas solo con una fuente y después de descartar series muy parecidas. "
            "Escribe la serie, LOCALIDAD=Torreón y los contadores disponibles."
        )
        self.create_missing_check.toggled.connect(self._missing_rows_changed)
        new_rows_options.addWidget(self.create_missing_check)
        self.allow_similar_check = QCheckBox("Autorizar series parecidas ya revisadas")
        self.allow_similar_check.setChecked(False)
        self.allow_similar_check.setEnabled(self.create_missing_check.isChecked())
        self.allow_similar_check.setToolTip(
            "Úselo únicamente después de revisar las advertencias. Las filas seguirán documentadas como discrepancia."
        )
        self.allow_similar_check.toggled.connect(self._invalidate)
        new_rows_options.addWidget(self.allow_similar_check)
        panel_layout.addLayout(new_rows_options)

        options = QVBoxLayout()
        options.setSpacing(8)
        self.overwrite_check = QCheckBox(
            "Reemplazar valores existentes y documentar la discrepancia"
        )
        self.overwrite_check.toggled.connect(self._invalidate)
        options.addWidget(self.overwrite_check)
        self.analyze_btn = QPushButton("Analizar y preparar vista previa")
        self.analyze_btn.setObjectName("primaryButton")
        self.analyze_btn.clicked.connect(self._analyze)
        options.addWidget(self.analyze_btn)
        panel_layout.addLayout(options)
        left_layout.addWidget(panel, 1)

        results_header = QHBoxLayout()
        self.summary = QLabel("Sin análisis")
        self.summary.setObjectName("nativeSectionTitle")
        self.summary.setWordWrap(True)
        results_header.addWidget(self.summary, 1)
        self.correct_serial_btn = QPushButton("Corregir serie seleccionada…")
        self.correct_serial_btn.setEnabled(False)
        self.correct_serial_btn.setToolTip(
            "Corrige la serie discrepante para este análisis y vuelve a comprobar la coincidencia exacta."
        )
        self.correct_serial_btn.clicked.connect(self._prompt_serial_correction)
        results_header.addWidget(self.correct_serial_btn)
        right_layout.addLayout(results_header)

        splitter = QSplitter(Qt.Orientation.Vertical)
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels([
            "Número de serie", "Fuente(s)", "Fila reporte", "Fila maestra",
            "Estado", "Celdas", "Ubicación", "Detalle"
        ])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(
            QTableWidget.EditTrigger.DoubleClicked
            | QTableWidget.EditTrigger.EditKeyPressed
        )
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._show_details)
        self.table.itemChanged.connect(self._serial_item_changed)
        splitter.addWidget(self.table)

        self.detail = QTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setPlaceholderText("Aquí aparecerán el mapeo detectado y el detalle del equipo seleccionado.")
        splitter.addWidget(self.detail)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([620, 180])
        right_layout.addWidget(splitter, 1)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(8)
        self.progress.hide()
        right_layout.addWidget(self.progress)

        footer = QHBoxLayout()
        self.status = QLabel("Seleccione la hoja maestra; los contadores pueden leerse desde Atlas o desde reportes.")
        self.status.setWordWrap(True)
        footer.addWidget(self.status, 1)
        self.generate_btn = QPushButton("Generar copia actualizada")
        self.generate_btn.setObjectName("primaryButton")
        self.generate_btn.setEnabled(False)
        self.generate_btn.clicked.connect(self._generate)
        footer.addWidget(self.generate_btn)
        right_layout.addLayout(footer)

        main_splitter.addWidget(left)
        main_splitter.addWidget(right)
        main_splitter.setStretchFactor(0, 0)
        main_splitter.setStretchFactor(1, 1)
        main_splitter.setSizes([410, 790])
        saved_splitter = self._settings.value("counter_inserter/main_splitter")
        if saved_splitter:
            main_splitter.restoreState(saved_splitter)
        main_splitter.splitterMoved.connect(
            lambda _position, _index: self._settings.setValue(
                "counter_inserter/main_splitter", main_splitter.saveState()
            )
        )
        root.addWidget(main_splitter, 1)

        self.master_edit.textChanged.connect(self._invalidate)
        self.target_range_edit.textChanged.connect(self._invalidate)
        self.master_serial_edit.textChanged.connect(self._invalidate)

    def _database_source_changed(self, checked: bool) -> None:
        self._settings.setValue("counter_inserter/use_database", checked)
        self.sync_location_check.setEnabled(checked)
        if not checked:
            self.sync_location_check.setChecked(False)
        self.replace_location_check.setEnabled(checked and self.sync_location_check.isChecked())
        self.sync_auxiliary_check.setEnabled(checked)
        self.import_missing_ip_check.setEnabled(checked)
        if not checked:
            self.sync_auxiliary_check.setChecked(False)
            self.import_missing_ip_check.setChecked(False)
        self._invalidate()

    def _auxiliary_option_changed(self, _checked: bool = False) -> None:
        self._settings.setValue("counter_inserter/sync_auxiliary", self.sync_auxiliary_check.isChecked())
        self._invalidate()

    def _location_option_changed(self, _checked: bool = False) -> None:
        enabled = self.database_source_check.isChecked() and self.sync_location_check.isChecked()
        self.replace_location_check.setEnabled(enabled)
        if not enabled:
            self.replace_location_check.setChecked(False)
        self._settings.setValue("counter_inserter/sync_location", self.sync_location_check.isChecked())
        self._settings.setValue("counter_inserter/replace_location", self.replace_location_check.isChecked())
        self._invalidate()

    def _missing_rows_changed(self, checked: bool) -> None:
        self._settings.setValue("counter_inserter/create_missing_rows", checked)
        self.allow_similar_check.setEnabled(checked)
        if not checked:
            self.allow_similar_check.setChecked(False)
        self._invalidate()

    def _select_master(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar hoja maestra", "", "Hojas compatibles (*.xlsx *.ods)"
        )
        if path:
            self.master_edit.setText(path)
            self._load_master_sheets(path)

    def _load_master_sheets(self, path: str) -> None:
        try:
            names = master_sheet_names(Path(path))
            suggested = suggest_master_sheet(Path(path))
        except Exception as error:
            self.status.setText(f"No se pudieron leer las pestañas: {error}")
            return
        self.sheet_combo.blockSignals(True)
        self.sheet_combo.clear()
        self.sheet_combo.addItems(names)
        if suggested in names:
            self.sheet_combo.setCurrentText(suggested)
        self.sheet_combo.blockSignals(False)
        self._invalidate()

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
        self.sheet_combo.setEnabled(not busy)
        self.target_range_edit.setEnabled(not busy)
        self.master_serial_edit.setEnabled(not busy)
        self.database_source_check.setEnabled(not busy)
        self.sync_location_check.setEnabled((not busy) and self.database_source_check.isChecked())
        self.replace_location_check.setEnabled(
            (not busy) and self.database_source_check.isChecked() and self.sync_location_check.isChecked()
        )
        self.sync_auxiliary_check.setEnabled((not busy) and self.database_source_check.isChecked())
        self.import_missing_ip_check.setEnabled((not busy) and self.database_source_check.isChecked())
        self.create_missing_check.setEnabled(not busy)
        self.allow_similar_check.setEnabled((not busy) and self.create_missing_check.isChecked())
        self.report_list.setEnabled(not busy)
        self.report_add_btn.setEnabled(not busy)
        self.report_remove_btn.setEnabled(not busy)
        self.report_clear_btn.setEnabled(not busy)
        self.overwrite_check.setEnabled(not busy)
        self.correct_serial_btn.setEnabled(
            (not busy) and self._selected_serial_is_editable()
        )
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
        use_database = self.database_source_check.isChecked()
        if not master:
            QMessageBox.warning(self, APP_NAME, "Seleccione la hoja maestra.")
            return
        if not reports and not use_database:
            QMessageBox.warning(
                self, APP_NAME,
                "Seleccione al menos un reporte fuente o active la base de datos de Atlas.",
            )
            return
        sheet_name = self.sheet_combo.currentText().strip()
        if not sheet_name:
            QMessageBox.warning(self, APP_NAME, "Seleccione la pestaña destino de la hoja maestra.")
            return
        target_spec = self.target_range_edit.text().strip() or "AUTO"
        master_serial_spec = self.master_serial_edit.text().strip() or "AUTO"
        overwrite = self.overwrite_check.isChecked()
        create_missing = self.create_missing_check.isChecked()
        allow_similar = self.allow_similar_check.isChecked()
        location_mode = (
            "replace" if use_database and self.sync_location_check.isChecked() and self.replace_location_check.isChecked()
            else "fill" if use_database and self.sync_location_check.isChecked()
            else "off"
        )
        auxiliary_mode = "fill" if use_database and self.sync_auxiliary_check.isChecked() else "off"
        import_missing_ips = use_database and self.import_missing_ip_check.isChecked()
        serial_overrides = dict(self._serial_overrides)
        self.analysis = None
        self.table.setRowCount(0)
        self.summary.setText("Analizando…")
        self.detail.setPlainText(
            "Procesando archivos. En libros grandes esta operación puede tardar varios minutos. "
            "La barra en movimiento confirma que CodeCafe Atlas continúa trabajando."
        )
        self._set_busy(True, "Analizando estructura, coincidencias y campos compatibles…")
        self._start_task(
            lambda: analyze_multiple_files(
                Path(master), reports, overwrite,
                master_sheet_name=sheet_name,
                target_spec=target_spec,
                source_spec="AUTO",
                master_serial_spec=master_serial_spec,
                report_tables=(
                    [read_atlas_counter_database(database_path())] if use_database else []
                ),
                create_missing_rows=create_missing,
                allow_similar_missing_rows=allow_similar,
                serial_overrides=serial_overrides,
                location_mode=location_mode,
                auxiliary_mode=auxiliary_mode,
                import_missing_ips=import_missing_ips,
            ),
            self._analysis_completed,
            "El análisis no pudo completarse.",
        )

    def _analysis_completed(self, result: object) -> None:
        self.analysis = result if isinstance(result, AnalysisResult) else None
        if self.analysis is None:
            self.status.setText("El análisis devolvió un resultado inválido.")
            return
        detected_mapping = target_range_label()
        self.target_range_edit.blockSignals(True)
        self.target_range_edit.setText(detected_mapping)
        self.target_range_edit.blockSignals(False)
        self._settings.setValue("counter_inserter/target_spec", detected_mapping)
        detected_master_serial = col_letter(self.analysis.master_layout.serial_col)
        self.master_serial_edit.blockSignals(True)
        self.master_serial_edit.setText(detected_master_serial)
        self.master_serial_edit.blockSignals(False)
        self._settings.setValue("counter_inserter/master_serial_col", detected_master_serial)
        self._populate()
        counts = self.analysis.counts()
        writable = counts.get("writable_cells", 0) + counts.get("status_updates", 0)
        writable += counts.get("location_updates", 0)
        if writable > 0:
            self.status.setText("Vista previa terminada. La hoja maestra no ha sido modificada.")
        else:
            self.status.setText(
                "El análisis terminó sin valores nuevos. Puede generar una copia verificada sin cambios."
            )

    def _populate(self) -> None:
        assert self.analysis is not None
        self._populating_table = True
        try:
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
                    (
                        f"{decision.location_action}: {decision.location_value}"
                        if decision.location_value else decision.location_action
                    ),
                    decision.details,
                ]
                for column, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    if column == 0 and self._serial_is_editable(decision):
                        item.setToolTip(
                            "Doble clic o F2 para corregir la serie; Atlas repetirá el análisis exacto."
                        )
                    else:
                        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    self.table.setItem(row_index, column, item)
        finally:
            self._populating_table = False

        counts = self.analysis.counts()
        source_count = self.report_list.count() + int(self.database_source_check.isChecked())
        database_counts = ""
        if self.analysis.source_record_count:
            database_counts = (
                f"{self.analysis.source_record_count} lecturas históricas · "
                f"{self.analysis.source_unique_count} series únicas · "
            )
        self.summary.setText(
            f"{source_count} fuente(s) · {database_counts}{counts.get('report_rows', 0)} registros procesados · "
            f"{counts.get('writable_equipment', 0)} equipos listos · "
            f"{counts.get('new_master_rows', 0)} filas nuevas · "
            f"{counts.get('writable_cells', 0)} celdas · "
            f"{counts.get('status_updates', 0)} estados a En Operación · "
            f"{counts.get('location_updates', 0)} ubicaciones · "
            f"{counts.get('location_replacements', 0)} reemplazos de ubicación · "
            f"{counts.get('date_updates', 0)} fechas · "
            f"{counts.get('floor_updates', 0)} pisos · "
            f"{counts.get('ip_updates', 0)} IP en hoja · "
            f"{counts.get('atlas_ip_imports', 0)} IP hacia Atlas · "
            f"{counts.get('zero_fill_cells', 0)} ceros · "
            f"{counts.get('conflict_cells', 0)} conflictos · "
            f"{counts.get('discrepancies', 0)} discrepancias"
            + (f" · {len(self._serial_overrides)} corrección(es) manual(es)" if self._serial_overrides else "")
        )
        layout = self.analysis.master_layout
        lines = [
            "DESTINO FLEXIBLE:",
            f"• Pestaña: {self.analysis.master_sheet}",
            f"• Filas detectadas: {layout.first_row}–{layout.last_row}",
            f"• Serie: columna {layout.serial_col}; localidad: columna {layout.locality_col}",
            f"• Estado operativo: {col_letter(layout.status_col) if layout.status_col else 'no detectado'}",
            f"• Ubicación de Equipo: {col_letter(layout.equipment_location_col) if layout.equipment_location_col else 'no detectada'}",
            f"• Fecha del contador: {col_letter(layout.counter_date_col) if layout.counter_date_col else 'no detectada'}",
            f"• Piso: {col_letter(layout.floor_col) if layout.floor_col else 'no detectado'}",
            f"• Dirección IP: {col_letter(layout.ip_col) if layout.ip_col else 'no detectada'}",
            f"• Contadores: {target_range_label()}",
            "",
            "MAPEO DETECTADO (fuentes → hoja maestra):",
        ]
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
            f"Únicamente se escribe {target_range_label()}. Las celdas realmente vacías se completan con 0 cuando existe al menos un contador válido.",
            "Toda discrepancia se documenta en un CSV adicional para revisión manual.",
            "Una serie parecida a otra existente se bloquea y se presenta como posible captura incorrecta; nunca se corrige ni duplica automáticamente.",
        ])
        self.detail.setPlainText("\n".join(lines))

    def _show_details(self) -> None:
        if self.analysis is None:
            self.correct_serial_btn.setEnabled(False)
            return
        row = self.table.currentRow()
        if row < 0 or row >= len(self.analysis.decisions):
            self.correct_serial_btn.setEnabled(False)
            return
        decision = self.analysis.decisions[row]
        self.correct_serial_btn.setEnabled(self._serial_is_editable(decision))
        lines = [
            f"Serie: {decision.serial_raw}",
            f"Fuente(s): {decision.source_names or self.analysis.report_path.name}",
            f"Fila del reporte: {decision.report_row}",
            f"Fila maestra: {decision.master_row or 'No encontrada'}",
            f"Estado: {decision.status}",
            decision.details,
            f"Acción sobre estado operativo: {decision.operation_status_action}",
            f"Ubicación existente: {decision.location_existing or 'vacía'}",
            f"Dependencia en Atlas: {decision.location_value or 'no disponible'}",
            f"Acción sobre ubicación: {decision.location_action}",
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

    @staticmethod
    def _serial_discrepancy_statuses() -> set[str]:
        return {
            "serie_vacia", "no_encontrado", "duplicado_reporte",
            "duplicado_maestro", "posible_serie_mal_escrita",
            "nueva_fila_con_advertencia",
        }

    def _serial_is_editable(self, decision) -> bool:
        if decision.status in self._serial_discrepancy_statuses():
            return True
        return any(
            normalize_serial(replacement) == decision.serial_key
            for replacement in self._serial_overrides.values()
        )

    def _selected_serial_is_editable(self) -> bool:
        if self.analysis is None:
            return False
        row = self.table.currentRow()
        return 0 <= row < len(self.analysis.decisions) and self._serial_is_editable(
            self.analysis.decisions[row]
        )

    def _prompt_serial_correction(self) -> None:
        if not self._selected_serial_is_editable() or self.analysis is None:
            QMessageBox.information(
                self, APP_NAME, "Seleccione una fila cuya discrepancia corresponda al número de serie."
            )
            return
        row = self.table.currentRow()
        decision = self.analysis.decisions[row]
        corrected, accepted = QInputDialog.getText(
            self,
            "Corregir número de serie",
            "Número de serie correcto:",
            text=decision.serial_raw,
        )
        if accepted:
            self._apply_serial_correction(row, corrected)

    def _serial_item_changed(self, item: QTableWidgetItem) -> None:
        if self._populating_table or item.column() != 0:
            return
        self._apply_serial_correction(item.row(), item.text())

    def _apply_serial_correction(self, row: int, corrected: str) -> None:
        if self.analysis is None or row < 0 or row >= len(self.analysis.decisions):
            return
        decision = self.analysis.decisions[row]
        if not self._serial_is_editable(decision):
            return
        corrected = str(corrected or "").strip()
        corrected_key = normalize_serial(corrected)
        if not corrected_key:
            QMessageBox.warning(self, APP_NAME, "Escriba un número de serie válido.")
            self._populate()
            return

        original_key = next(
            (
                key for key, replacement in self._serial_overrides.items()
                if normalize_serial(replacement) == decision.serial_key
            ),
            decision.serial_key,
        )
        if corrected_key == original_key:
            self._serial_overrides.pop(original_key, None)
        else:
            self._serial_overrides[original_key] = corrected
        self.status.setText(
            f"Serie corregida a {corrected}. Atlas volverá a comprobar todas las coincidencias."
        )
        self._analyze()

    def _generate(self) -> None:
        if self.analysis is None:
            QMessageBox.warning(self, APP_NAME, "Primero ejecute el análisis.")
            return
        master = Path(self.analysis.master_path)
        extension = master.suffix.lower()
        range_tag = target_range_label().replace(":", "-")
        default_name = master.stem + f"_CONTADORES_{range_tag}_TORREON" + extension
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

        counts = self.analysis.counts()
        writable = counts.get("writable_cells", 0) + counts.get("status_updates", 0)
        writable += counts.get("location_updates", 0)
        new_rows = counts.get("new_master_rows", 0)
        if writable > 0:
            confirmation_text = (
                "Se generará una copia nueva de la hoja maestra.\n\n"
                f"Solo se escribirán contadores autorizados en {target_range_label()} para equipos de Torreón "
                "con coincidencia exacta de número de serie. Las celdas vacías se completarán con 0. "
                "Si existen discrepancias, se generará un CSV adicional para revisión manual. "
                f"Filas nuevas confirmadas: {new_rows}. "
                f"Estados que cambiarán a En Operación: {self.analysis.counts().get('status_updates', 0)}. "
                f"Ubicaciones que se escribirán: {self.analysis.counts().get('location_updates', 0)} "
                f"(reemplazos: {self.analysis.counts().get('location_replacements', 0)}). "
                + ("Las altas de series parecidas fueron autorizadas y quedarán documentadas. " if self.allow_similar_check.isChecked() else "")
                + "El archivo original no será reemplazado.\n\n¿Continuar?"
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
        equipment = len(set(analysis.updates()) | set(analysis.status_updates()))
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
