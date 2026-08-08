from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import fitz
from PySide6.QtCore import QEvent, QFile, Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QProgressDialog,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from .pdf_duplicate_tools import (
    DuplicateScanCancelled,
    find_exact_duplicate_groups,
    path_is_within_root,
)
from .ui_helpers import page_header


@dataclass(frozen=True)
class PdfEntry:
    path: Path
    size: int
    modified: float

    @property
    def display_size(self) -> str:
        value = float(self.size)
        for unit in ("B", "KB", "MB", "GB"):
            if value < 1024 or unit == "GB":
                return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
            value /= 1024
        return f"{value:.1f} GB"


class PdfLibraryPage(QWidget):
    """Visor PDF local: indexación por carpeta, búsqueda y visor integrado."""

    def __init__(self):
        super().__init__()
        self.root_folder: Path | None = None
        self.entries: list[PdfEntry] = []
        self.filtered_entries: list[PdfEntry] = []
        self.document: fitz.Document | None = None
        self.current_path: Path | None = None
        self.current_page = 0
        self.zoom = 1.0
        self.rotation = 0
        self.fit_width_enabled = True
        self.duplicate_groups: list[list[Path]] = []
        self.duplicate_group_by_path: dict[Path, int] = {}
        self.duplicate_scan_completed = False
        self.duplicate_scan_errors: list[tuple[Path, str]] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 28)
        layout.setSpacing(14)
        layout.addWidget(page_header(
            "Visor PDF",
            "Organiza, busca y consulta documentos PDF locales sin mover los archivos originales.",
        ))

        actions = QHBoxLayout()
        self.folder_button = QPushButton("Seleccionar carpeta…")
        self.folder_button.setObjectName("primaryButton")
        self.folder_button.clicked.connect(self.select_folder)
        actions.addWidget(self.folder_button)

        self.reload_button = QPushButton("Actualizar índice")
        self.reload_button.clicked.connect(self.reload_index)
        self.reload_button.setEnabled(False)
        actions.addWidget(self.reload_button)

        self.duplicate_scan_button = QPushButton("Detectar duplicados")
        self.duplicate_scan_button.clicked.connect(lambda: self.detect_duplicates())
        self.duplicate_scan_button.setEnabled(False)
        actions.addWidget(self.duplicate_scan_button)

        self.duplicates_only_button = QPushButton("Mostrar solo duplicados")
        self.duplicates_only_button.setCheckable(True)
        self.duplicates_only_button.setEnabled(False)
        self.duplicates_only_button.toggled.connect(self.toggle_duplicates_only)
        actions.addWidget(self.duplicates_only_button)

        self.folder_label = QLabel("Ninguna carpeta seleccionada")
        self.folder_label.setObjectName("pageSubtitle")
        self.folder_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        actions.addWidget(self.folder_label, 1)
        layout.addLayout(actions)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Buscar por nombre de archivo o ubicación…")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self.apply_filter)
        layout.addWidget(self.search_edit)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        layout.addWidget(splitter, 1)

        browser_panel = QFrame()
        browser_panel.setObjectName("nativePanel")
        browser_layout = QVBoxLayout(browser_panel)
        browser_layout.setContentsMargins(14, 14, 14, 14)
        browser_layout.setSpacing(10)

        self.result_label = QLabel("0 documentos")
        self.result_label.setObjectName("nativeSectionTitle")
        browser_layout.addWidget(self.result_label)

        self.file_list = QListWidget()
        self.file_list.setObjectName("pdfLibraryList")
        self.file_list.currentItemChanged.connect(self.open_selected_item)
        browser_layout.addWidget(self.file_list, 1)

        details = QFrame()
        details.setObjectName("metricCard")
        details_layout = QVBoxLayout(details)
        self.name_label = QLabel("Selecciona un PDF")
        self.name_label.setWordWrap(True)
        self.name_label.setObjectName("dropTitle")
        self.path_label = QLabel("")
        self.path_label.setWordWrap(True)
        self.path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.path_label.setObjectName("pageSubtitle")
        self.metadata_label = QLabel("")
        self.metadata_label.setObjectName("pageSubtitle")
        self.duplicate_detail_label = QLabel("")
        self.duplicate_detail_label.setObjectName("nativeNote")
        self.duplicate_detail_label.setWordWrap(True)
        self.duplicate_detail_label.hide()
        details_layout.addWidget(self.name_label)
        details_layout.addWidget(self.path_label)
        details_layout.addWidget(self.metadata_label)
        details_layout.addWidget(self.duplicate_detail_label)
        browser_layout.addWidget(details)

        detail_buttons = QHBoxLayout()
        self.open_external_button = QPushButton("Abrir PDF")
        self.open_external_button.clicked.connect(self.open_external)
        self.open_external_button.setEnabled(False)
        detail_buttons.addWidget(self.open_external_button)
        self.open_folder_button = QPushButton("Abrir carpeta")
        self.open_folder_button.clicked.connect(self.open_containing_folder)
        self.open_folder_button.setEnabled(False)
        detail_buttons.addWidget(self.open_folder_button)
        self.delete_button = QPushButton("Eliminar PDF…")
        self.delete_button.setObjectName("trashButton")
        self.delete_button.clicked.connect(self.delete_selected_pdf)
        self.delete_button.setEnabled(False)
        detail_buttons.addWidget(self.delete_button)
        browser_layout.addLayout(detail_buttons)
        splitter.addWidget(browser_panel)

        viewer_panel = QFrame()
        viewer_panel.setObjectName("nativePanel")
        viewer_layout = QVBoxLayout(viewer_panel)
        viewer_layout.setContentsMargins(10, 10, 10, 10)
        viewer_layout.setSpacing(8)

        toolbar = QHBoxLayout()
        self.previous_button = QPushButton("← Anterior")
        self.previous_button.clicked.connect(self.previous_page)
        toolbar.addWidget(self.previous_button)
        self.next_button = QPushButton("Siguiente →")
        self.next_button.clicked.connect(self.next_page)
        toolbar.addWidget(self.next_button)
        self.page_label = QLabel("Página 0 de 0")
        self.page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        toolbar.addWidget(self.page_label, 1)

        self.rotate_left_button = QPushButton("↶ Girar")
        self.rotate_left_button.clicked.connect(lambda: self.rotate(-90))
        toolbar.addWidget(self.rotate_left_button)
        self.rotate_right_button = QPushButton("Girar ↷")
        self.rotate_right_button.clicked.connect(lambda: self.rotate(90))
        toolbar.addWidget(self.rotate_right_button)
        self.fit_button = QPushButton("Ajustar al ancho")
        self.fit_button.clicked.connect(self.fit_to_width)
        toolbar.addWidget(self.fit_button)
        self.zoom_out_button = QPushButton("−")
        self.zoom_out_button.clicked.connect(lambda: self.change_zoom(-0.15))
        toolbar.addWidget(self.zoom_out_button)
        self.zoom_label = QLabel("100 %")
        self.zoom_label.setMinimumWidth(58)
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        toolbar.addWidget(self.zoom_label)
        self.zoom_in_button = QPushButton("+")
        self.zoom_in_button.clicked.connect(lambda: self.change_zoom(0.15))
        toolbar.addWidget(self.zoom_in_button)
        viewer_layout.addLayout(toolbar)

        self.scroll_area = QScrollArea()
        # El visor debe conservar el tamaño real de la página renderizada.
        # Con widgetResizable=True, QScrollArea comprimía el QLabel al área
        # visible y no creaba la barra vertical aunque el PDF fuera más alto.
        self.scroll_area.setWidgetResizable(False)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll_area.viewport().installEventFilter(self)
        self.document_label = QLabel("Selecciona un documento para visualizarlo")
        self.document_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.document_label.setMinimumSize(400, 500)
        self.document_label.setObjectName("pdfViewerCanvas")
        self.scroll_area.setWidget(self.document_label)
        viewer_layout.addWidget(self.scroll_area, 1)
        splitter.addWidget(viewer_panel)
        splitter.setSizes([390, 900])

        self._set_viewer_enabled(False)

    def select_folder(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta con documentos PDF")
        if not selected:
            return
        self.root_folder = Path(selected)
        self.folder_label.setText(str(self.root_folder))
        self.reload_button.setEnabled(True)
        self.duplicate_scan_button.setEnabled(True)
        self.reload_index()

    def reload_index(self) -> None:
        self._reload_index(reset_duplicate_state=True)

    def _reload_index(self, *, reset_duplicate_state: bool) -> None:
        if self.root_folder is None:
            return
        if reset_duplicate_state:
            self._clear_duplicate_state()
        try:
            paths = sorted(
                (path for path in self.root_folder.rglob("*") if path.is_file() and path.suffix.lower() == ".pdf"),
                key=lambda path: (path.name.lower(), str(path).lower()),
            )
            entries: list[PdfEntry] = []
            for path in paths:
                try:
                    stat = path.stat()
                    entries.append(PdfEntry(path=path, size=stat.st_size, modified=stat.st_mtime))
                except OSError:
                    continue
            self.entries = entries
            if self.current_path is not None and not any(
                entry.path == self.current_path for entry in entries
            ):
                self._clear_current_document()
            self.apply_filter()
        except OSError as error:
            QMessageBox.critical(self, "No se pudo indexar", str(error))

    def apply_filter(self) -> None:
        query = self.search_edit.text().strip().casefold()
        source_entries = self.entries
        if self.duplicates_only_button.isChecked():
            source_entries = [
                entry for entry in source_entries
                if entry.path in self.duplicate_group_by_path
            ]
        if not query:
            self.filtered_entries = list(source_entries)
        else:
            self.filtered_entries = [
                entry for entry in source_entries
                if query in entry.path.name.casefold() or query in str(entry.path.parent).casefold()
            ]

        selected_path = self.current_path
        self.file_list.blockSignals(True)
        self.file_list.clear()
        selected_row = -1
        for row, entry in enumerate(self.filtered_entries):
            relative_parent = ""
            if self.root_folder is not None:
                try:
                    relative_parent = str(entry.path.parent.relative_to(self.root_folder))
                except ValueError:
                    relative_parent = str(entry.path.parent)
            subtitle = relative_parent if relative_parent not in ("", ".") else "Carpeta principal"
            group_number = self.duplicate_group_by_path.get(entry.path)
            prefix = f"Duplicado {group_number} · " if group_number is not None else ""
            item = QListWidgetItem(f"{prefix}{entry.path.name}\n{subtitle}")
            item.setData(Qt.ItemDataRole.UserRole, str(entry.path))
            item.setToolTip(str(entry.path))
            self.file_list.addItem(item)
            if selected_path and entry.path == selected_path:
                selected_row = row
        self.file_list.blockSignals(False)
        if self.duplicate_scan_completed:
            duplicate_count = len(self.duplicate_group_by_path)
            group_count = len(self.duplicate_groups)
            self.result_label.setText(
                f"{len(self.filtered_entries)} documento(s) · "
                f"{duplicate_count} duplicado(s) exacto(s) en {group_count} grupo(s)"
            )
        else:
            self.result_label.setText(f"{len(self.filtered_entries)} documento(s)")
        if selected_row >= 0:
            self.file_list.setCurrentRow(selected_row)

    def open_selected_item(self, current: QListWidgetItem | None, previous: QListWidgetItem | None) -> None:
        del previous
        if current is None:
            return
        self.load_document(Path(current.data(Qt.ItemDataRole.UserRole)))

    def load_document(self, path: Path) -> None:
        self.close_document()
        try:
            self.document = fitz.open(path)
            if self.document.page_count < 1:
                raise ValueError("El PDF no contiene páginas.")
        except Exception as error:
            self.document = None
            QMessageBox.warning(self, "No se pudo abrir el PDF", f"{path.name}\n\n{error}")
            return

        self.current_path = path
        self.current_page = 0
        self.rotation = 0
        self.fit_width_enabled = True
        entry = next((item for item in self.entries if item.path == path), None)
        self.name_label.setText(path.name)
        self.path_label.setText(str(path.parent))
        if entry:
            modified = datetime.fromtimestamp(entry.modified).strftime("%d/%m/%Y %H:%M")
            self.metadata_label.setText(f"{entry.display_size} · Modificado: {modified}")
        else:
            self.metadata_label.clear()
        self.open_external_button.setEnabled(True)
        self.open_folder_button.setEnabled(True)
        self.delete_button.setEnabled(True)
        self._update_duplicate_detail(path)
        self._set_viewer_enabled(True)
        self.render_page()

    def close_document(self) -> None:
        if self.document is not None:
            self.document.close()
        self.document = None

    def _set_viewer_enabled(self, enabled: bool) -> None:
        for widget in (
            self.previous_button, self.next_button, self.rotate_left_button,
            self.rotate_right_button, self.fit_button, self.zoom_out_button,
            self.zoom_in_button,
        ):
            widget.setEnabled(enabled)

    def render_page(self) -> None:
        if self.document is None:
            return
        page = self.document.load_page(self.current_page)
        if self.fit_width_enabled:
            available = max(300, self.scroll_area.viewport().width() - 34)
            rotated_rect = page.rect if self.rotation % 180 == 0 else fitz.Rect(0, 0, page.rect.height, page.rect.width)
            self.zoom = max(0.25, min(4.0, available / rotated_rect.width))
        matrix = fitz.Matrix(self.zoom, self.zoom).prerotate(self.rotation)
        pixmap = page.get_pixmap(matrix=matrix, alpha=False)
        image = QImage(
            pixmap.samples,
            pixmap.width,
            pixmap.height,
            pixmap.stride,
            QImage.Format.Format_RGB888,
        ).copy()
        self.document_label.setPixmap(QPixmap.fromImage(image))
        # El tamaño fijo obliga al QScrollArea a calcular correctamente el
        # recorrido de sus barras al hacer zoom, girar o ajustar al ancho.
        self.document_label.setFixedSize(image.size())
        self.page_label.setText(f"Página {self.current_page + 1} de {self.document.page_count}")
        self.zoom_label.setText(f"{round(self.zoom * 100)} %")
        self.previous_button.setEnabled(self.current_page > 0)
        self.next_button.setEnabled(self.current_page < self.document.page_count - 1)

    def previous_page(self) -> None:
        if self.document is not None and self.current_page > 0:
            self.current_page -= 1
            self.render_page()

    def next_page(self) -> None:
        if self.document is not None and self.current_page < self.document.page_count - 1:
            self.current_page += 1
            self.render_page()

    def rotate(self, degrees: int) -> None:
        if self.document is None:
            return
        self.rotation = (self.rotation + degrees) % 360
        self.render_page()

    def change_zoom(self, delta: float) -> None:
        if self.document is None:
            return
        self.fit_width_enabled = False
        self.zoom = max(0.25, min(4.0, self.zoom + delta))
        self.render_page()

    def fit_to_width(self) -> None:
        if self.document is None:
            return
        self.fit_width_enabled = True
        self.render_page()

    def eventFilter(self, watched, event):
        if watched is self.scroll_area.viewport() and self.fit_width_enabled and self.document is not None:
            if event.type() == QEvent.Type.Resize:
                self.render_page()
        return super().eventFilter(watched, event)

    def _clear_duplicate_state(self) -> None:
        self.duplicate_groups = []
        self.duplicate_group_by_path = {}
        self.duplicate_scan_completed = False
        self.duplicate_scan_errors = []
        self.duplicates_only_button.blockSignals(True)
        self.duplicates_only_button.setChecked(False)
        self.duplicates_only_button.blockSignals(False)
        self.duplicates_only_button.setText("Mostrar solo duplicados")
        self.duplicates_only_button.setEnabled(False)
        self.duplicate_detail_label.hide()

    def toggle_duplicates_only(self, checked: bool) -> None:
        self.duplicates_only_button.setText(
            "Mostrar todos" if checked else "Mostrar solo duplicados"
        )
        if (
            checked
            and self.current_path is not None
            and self.current_path not in self.duplicate_group_by_path
        ):
            self._clear_current_document()
        self.apply_filter()
        if checked and self.file_list.count() and self.file_list.currentRow() < 0:
            self.file_list.setCurrentRow(0)

    def detect_duplicates(self, *, refresh_index: bool = True, show_summary: bool = True) -> None:
        if self.root_folder is None:
            return
        if refresh_index:
            self._reload_index(reset_duplicate_state=True)

        progress_dialog = QProgressDialog(
            "Buscando copias exactas…",
            "Cancelar",
            0,
            max(1, len(self.entries)),
            self,
        )
        progress_dialog.setWindowTitle("Detectar duplicados")
        progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        progress_dialog.setMinimumDuration(250)
        progress_dialog.setAutoClose(False)
        progress_dialog.setAutoReset(False)

        def report_progress(current: int, total: int, path: Path) -> None:
            progress_dialog.setMaximum(max(1, total))
            progress_dialog.setValue(current)
            progress_dialog.setLabelText(
                f"Calculando firma {current} de {total}:\n{path.name}"
            )
            QApplication.processEvents()

        try:
            groups, errors = find_exact_duplicate_groups(
                (entry.path for entry in self.entries),
                progress=report_progress,
                should_cancel=progress_dialog.wasCanceled,
            )
        except DuplicateScanCancelled:
            progress_dialog.close()
            self._clear_duplicate_state()
            self.apply_filter()
            return
        finally:
            progress_dialog.close()

        self.duplicate_groups = groups
        self.duplicate_group_by_path = {
            path: group_number
            for group_number, group in enumerate(groups, start=1)
            for path in group
        }
        self.duplicate_scan_errors = errors
        self.duplicate_scan_completed = True
        self.duplicates_only_button.setEnabled(bool(groups))
        self.duplicates_only_button.setChecked(bool(groups))
        self.apply_filter()
        if self.current_path is not None:
            self._update_duplicate_detail(self.current_path)

        if not show_summary:
            return
        duplicate_count = len(self.duplicate_group_by_path)
        if groups:
            message = (
                f"Se encontraron {duplicate_count} archivos duplicados exactos "
                f"distribuidos en {len(groups)} grupos.\n\n"
                "La lista muestra únicamente los duplicados. Selecciona cualquier "
                "archivo para revisarlo o eliminarlo."
            )
            if errors:
                message += f"\n\nNo se pudieron revisar {len(errors)} archivo(s)."
            QMessageBox.information(self, "Duplicados encontrados", message)
        else:
            message = "No se encontraron PDFs duplicados exactos por contenido."
            if errors:
                message += f"\n\nNo se pudieron revisar {len(errors)} archivo(s)."
            QMessageBox.information(self, "Sin duplicados", message)

    def _update_duplicate_detail(self, path: Path) -> None:
        group_number = self.duplicate_group_by_path.get(path)
        if group_number is None:
            self.duplicate_detail_label.clear()
            self.duplicate_detail_label.hide()
            return
        group = self.duplicate_groups[group_number - 1]
        other_count = max(0, len(group) - 1)
        self.duplicate_detail_label.setText(
            f"Duplicado exacto · Grupo {group_number} · "
            f"{other_count} copia(s) adicional(es) con el mismo contenido."
        )
        self.duplicate_detail_label.show()

    def _clear_current_document(self) -> None:
        self.close_document()
        self.current_path = None
        self.current_page = 0
        self.rotation = 0
        self.name_label.setText("Selecciona un PDF")
        self.path_label.clear()
        self.metadata_label.clear()
        self.duplicate_detail_label.clear()
        self.duplicate_detail_label.hide()
        self.open_external_button.setEnabled(False)
        self.open_folder_button.setEnabled(False)
        self.delete_button.setEnabled(False)
        self._set_viewer_enabled(False)
        self.document_label.clear()
        self.document_label.setText("Selecciona un documento para visualizarlo")
        self.document_label.setFixedSize(400, 500)
        self.page_label.setText("Página 0 de 0")
        self.zoom_label.setText("100 %")

    def _path_is_inside_root(self, path: Path) -> bool:
        return self.root_folder is not None and path_is_within_root(path, self.root_folder)

    def delete_selected_pdf(self) -> None:
        path = self.current_path
        if path is None:
            return
        if path.suffix.lower() != ".pdf" or not self._path_is_inside_root(path):
            QMessageBox.warning(
                self,
                "No se puede eliminar",
                "Atlas solo puede eliminar PDFs ubicados dentro de la carpeta seleccionada.",
            )
            return
        if not path.exists():
            QMessageBox.warning(self, "Archivo no encontrado", str(path))
            self._clear_current_document()
            self._reload_index(reset_duplicate_state=True)
            return

        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setWindowTitle("Eliminar PDF")
        dialog.setText("¿Qué deseas hacer con este PDF?")
        dialog.setInformativeText(
            f"{path.name}\n\nMoverlo a la papelera es la opción recomendada."
        )
        dialog.setDetailedText(str(path))
        trash_action = None
        if QFile.supportsMoveToTrash():
            trash_action = dialog.addButton(
                "Mover a la papelera",
                QMessageBox.ButtonRole.AcceptRole,
            )
        delete_action = dialog.addButton(
            "Eliminar permanentemente",
            QMessageBox.ButtonRole.DestructiveRole,
        )
        dialog.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)
        dialog.exec()
        selected_action = dialog.clickedButton()
        valid_actions = [delete_action]
        if trash_action is not None:
            valid_actions.append(trash_action)
        if selected_action not in valid_actions:
            return

        duplicate_scan_was_active = self.duplicate_scan_completed
        self.close_document()
        action_description = "movió a la papelera"
        try:
            if trash_action is not None and selected_action is trash_action:
                trash_file = QFile(str(path))
                if not trash_file.moveToTrash():
                    raise OSError("El sistema no pudo mover el archivo a la papelera.")
            else:
                path.unlink()
                action_description = "eliminó permanentemente"
        except OSError as error:
            QMessageBox.critical(
                self,
                "No se pudo eliminar el PDF",
                f"{path.name}\n\n{error}",
            )
            if path.exists():
                self.load_document(path)
            return

        self._clear_current_document()
        self._reload_index(reset_duplicate_state=True)
        if duplicate_scan_was_active:
            self.detect_duplicates(refresh_index=False, show_summary=False)
        QMessageBox.information(
            self,
            "PDF eliminado",
            f"Se {action_description}:\n{path.name}",
        )

    def open_external(self) -> None:
        if self.current_path is not None:
            self._open_path(self.current_path)

    def open_containing_folder(self) -> None:
        if self.current_path is None:
            return
        try:
            if sys.platform.startswith("win"):
                subprocess.Popen(["explorer", "/select,", str(self.current_path)])
            else:
                self._open_path(self.current_path.parent)
        except OSError as error:
            QMessageBox.warning(self, "No se pudo abrir la ubicación", str(error))

    @staticmethod
    def _open_path(path: Path) -> None:
        if sys.platform.startswith("win"):
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])

    def closeEvent(self, event) -> None:
        self.close_document()
        super().closeEvent(event)
