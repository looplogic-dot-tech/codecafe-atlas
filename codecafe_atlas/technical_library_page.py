from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import fitz
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from .paths import data_dir
from .platform_open import open_directory_native, open_file_native
from .ui_helpers import page_header


SUPPORTED_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".odt", ".rtf", ".txt", ".md",
    ".xls", ".xlsx", ".ods", ".csv", ".tsv",
    ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif",
    ".ppt", ".pptx", ".odp",
}


@dataclass(frozen=True)
class TechnicalDocumentEntry:
    path: Path
    size: int
    modified: float

    @property
    def display_size(self) -> str:
        value = float(self.size)
        for unit in ("B", "KB", "MB", "GB"):
            if value < 1024 or unit == "GB":
                return f"{int(value)} B" if unit == "B" else f"{value:.1f} {unit}"
            value /= 1024
        return f"{value:.1f} GB"


class TechnicalLibraryPage(QWidget):
    """Indexes a user-owned technical-documentation folder without moving files."""

    def __init__(self):
        super().__init__()
        self.settings_path = data_dir() / "technical_library_settings.json"
        self.root_folder: Path | None = self._load_root_folder()
        self.entries: list[TechnicalDocumentEntry] = []
        self.filtered_entries: list[TechnicalDocumentEntry] = []
        self.current_path: Path | None = None
        self.document: fitz.Document | None = None
        self.current_page = 0
        self.zoom = 1.0
        self.fit_width_enabled = True

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 28)
        layout.setSpacing(14)
        layout.addWidget(page_header(
            "Biblioteca técnica",
            "Indexa tu carpeta de documentación sin mover ni duplicar los archivos originales.",
        ))

        actions = QHBoxLayout()
        choose_button = QPushButton("Seleccionar carpeta raíz…")
        choose_button.setObjectName("primaryButton")
        choose_button.clicked.connect(self.select_root_folder)
        actions.addWidget(choose_button)
        self.reload_button = QPushButton("Actualizar índice")
        self.reload_button.clicked.connect(self.reload_index)
        actions.addWidget(self.reload_button)
        self.folder_label = QLabel(
            str(self.root_folder) if self.root_folder else "Ninguna carpeta configurada"
        )
        self.folder_label.setObjectName("pageSubtitle")
        self.folder_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        actions.addWidget(self.folder_label, 1)
        layout.addLayout(actions)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Buscar por nombre, tipo o ubicación…")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self.apply_filter)
        layout.addWidget(self.search_edit)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        layout.addWidget(splitter, 1)

        browser_panel = QFrame()
        browser_panel.setObjectName("nativePanel")
        browser_layout = QVBoxLayout(browser_panel)
        self.result_label = QLabel("0 documentos")
        self.result_label.setObjectName("nativeSectionTitle")
        browser_layout.addWidget(self.result_label)
        self.file_list = QListWidget()
        self.file_list.currentItemChanged.connect(self.open_selected_item)
        browser_layout.addWidget(self.file_list, 1)

        self.name_label = QLabel("Selecciona un documento")
        self.name_label.setWordWrap(True)
        self.name_label.setObjectName("dropTitle")
        browser_layout.addWidget(self.name_label)
        self.metadata_label = QLabel("")
        self.metadata_label.setWordWrap(True)
        self.metadata_label.setObjectName("pageSubtitle")
        browser_layout.addWidget(self.metadata_label)

        buttons = QHBoxLayout()
        self.open_button = QPushButton("Abrir documento")
        self.open_button.clicked.connect(self.open_current_file)
        self.open_button.setEnabled(False)
        buttons.addWidget(self.open_button)
        self.open_folder_button = QPushButton("Abrir carpeta")
        self.open_folder_button.clicked.connect(self.open_current_folder)
        self.open_folder_button.setEnabled(False)
        buttons.addWidget(self.open_folder_button)
        browser_layout.addLayout(buttons)
        splitter.addWidget(browser_panel)

        preview_panel = QFrame()
        preview_panel.setObjectName("nativePanel")
        preview_layout = QVBoxLayout(preview_panel)
        toolbar = QHBoxLayout()
        self.previous_button = QPushButton("← Anterior")
        self.previous_button.clicked.connect(self.previous_page)
        toolbar.addWidget(self.previous_button)
        self.next_button = QPushButton("Siguiente →")
        self.next_button.clicked.connect(self.next_page)
        toolbar.addWidget(self.next_button)
        self.page_label = QLabel("Vista previa")
        self.page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        toolbar.addWidget(self.page_label, 1)
        self.fit_button = QPushButton("Ajustar al ancho")
        self.fit_button.clicked.connect(self.fit_to_width)
        toolbar.addWidget(self.fit_button)
        self.zoom_out_button = QPushButton("−")
        self.zoom_out_button.clicked.connect(lambda: self.change_zoom(-0.15))
        toolbar.addWidget(self.zoom_out_button)
        self.zoom_label = QLabel("100 %")
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.zoom_label.setMinimumWidth(58)
        toolbar.addWidget(self.zoom_label)
        self.zoom_in_button = QPushButton("+")
        self.zoom_in_button.clicked.connect(lambda: self.change_zoom(0.15))
        toolbar.addWidget(self.zoom_in_button)
        preview_layout.addLayout(toolbar)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(False)
        self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll_area.viewport().installEventFilter(self)
        self.preview_label = QLabel(
            "Los PDFs se muestran aquí.\nLos demás formatos se abren con su aplicación predeterminada."
        )
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setWordWrap(True)
        self.preview_label.setMinimumSize(480, 520)
        self.preview_label.setObjectName("pdfViewerCanvas")
        self.scroll_area.setWidget(self.preview_label)
        preview_layout.addWidget(self.scroll_area, 1)
        splitter.addWidget(preview_panel)
        splitter.setSizes([430, 850])
        self._set_pdf_controls(False)

        if self.root_folder and self.root_folder.is_dir():
            self.reload_index()
        else:
            self.reload_button.setEnabled(False)

    def _load_root_folder(self) -> Path | None:
        try:
            payload = json.loads(self.settings_path.read_text(encoding="utf-8"))
            raw = str(payload.get("root_folder") or "").strip()
            return Path(raw) if raw else None
        except (OSError, ValueError, TypeError):
            return None

    def _save_root_folder(self) -> None:
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"root_folder": str(self.root_folder or "")}
        temporary = self.settings_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.settings_path)

    def select_root_folder(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            "Seleccionar carpeta de Documentación Técnica",
            str(self.root_folder or ""),
        )
        if not selected:
            return
        self.root_folder = Path(selected)
        self.folder_label.setText(str(self.root_folder))
        self.reload_button.setEnabled(True)
        self._save_root_folder()
        self.reload_index()

    def reload_index(self) -> None:
        if self.root_folder is None or not self.root_folder.is_dir():
            return
        entries: list[TechnicalDocumentEntry] = []
        try:
            for path in self.root_folder.rglob("*"):
                if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                    continue
                try:
                    stat = path.stat()
                    entries.append(TechnicalDocumentEntry(path, stat.st_size, stat.st_mtime))
                except OSError:
                    continue
        except OSError as error:
            QMessageBox.critical(self, "No se pudo indexar", str(error))
            return
        self.entries = sorted(entries, key=lambda item: (item.path.name.casefold(), str(item.path).casefold()))
        if self.current_path and not any(item.path == self.current_path for item in self.entries):
            self.clear_preview()
        self.apply_filter()

    def apply_filter(self) -> None:
        query = self.search_edit.text().strip().casefold()
        self.filtered_entries = [
            entry for entry in self.entries
            if not query
            or query in entry.path.name.casefold()
            or query in str(entry.path.parent).casefold()
            or query in entry.path.suffix.casefold()
        ]
        selected_path = self.current_path
        self.file_list.blockSignals(True)
        self.file_list.clear()
        selected_row = -1
        for row, entry in enumerate(self.filtered_entries):
            try:
                relative = entry.path.parent.relative_to(self.root_folder) if self.root_folder else entry.path.parent
            except ValueError:
                relative = entry.path.parent
            subtitle = "Carpeta principal" if str(relative) in ("", ".") else str(relative)
            item = QListWidgetItem(f"{entry.path.name}\n{subtitle}")
            item.setData(Qt.ItemDataRole.UserRole, str(entry.path))
            item.setToolTip(str(entry.path))
            self.file_list.addItem(item)
            if selected_path == entry.path:
                selected_row = row
        self.file_list.blockSignals(False)
        self.result_label.setText(f"{len(self.filtered_entries)} documento(s)")
        if selected_row >= 0:
            self.file_list.setCurrentRow(selected_row)

    def open_selected_item(self, current: QListWidgetItem | None, previous) -> None:
        del previous
        if current is None:
            return
        self.load_document(Path(current.data(Qt.ItemDataRole.UserRole)))

    def load_document(self, path: Path) -> None:
        self.close_document()
        self.current_path = path
        entry = next((item for item in self.entries if item.path == path), None)
        self.name_label.setText(path.name)
        if entry:
            modified = datetime.fromtimestamp(entry.modified).strftime("%d/%m/%Y %H:%M")
            self.metadata_label.setText(
                f"{path.suffix.upper().lstrip('.')} · {entry.display_size} · "
                f"Modificado: {modified}\n{path.parent}"
            )
        self.open_button.setEnabled(True)
        self.open_folder_button.setEnabled(True)
        if path.suffix.lower() != ".pdf":
            self.preview_label.clear()
            self.preview_label.setText(
                f"Vista previa interna no disponible para {path.suffix.upper()}.\n\n"
                "Usa Abrir documento para consultarlo con su aplicación predeterminada."
            )
            self.preview_label.setFixedSize(480, 520)
            self.page_label.setText("Vista previa")
            self._set_pdf_controls(False)
            return
        try:
            self.document = fitz.open(path)
            if self.document.page_count < 1:
                raise ValueError("El PDF no contiene páginas.")
        except Exception as error:
            self.document = None
            QMessageBox.warning(self, "No se pudo abrir el PDF", f"{path.name}\n\n{error}")
            return
        self.current_page = 0
        self.fit_width_enabled = True
        self._set_pdf_controls(True)
        self.render_page()

    def close_document(self) -> None:
        if self.document is not None:
            self.document.close()
        self.document = None

    def clear_preview(self) -> None:
        self.close_document()
        self.current_path = None
        self.current_page = 0
        self.name_label.setText("Selecciona un documento")
        self.metadata_label.clear()
        self.open_button.setEnabled(False)
        self.open_folder_button.setEnabled(False)
        self._set_pdf_controls(False)
        self.preview_label.clear()
        self.preview_label.setText(
            "Los PDFs se muestran aquí.\nLos demás formatos se abren con su aplicación predeterminada."
        )
        self.preview_label.setFixedSize(480, 520)
        self.page_label.setText("Vista previa")

    def _set_pdf_controls(self, enabled: bool) -> None:
        for widget in (
            self.previous_button, self.next_button, self.fit_button,
            self.zoom_out_button, self.zoom_in_button,
        ):
            widget.setEnabled(enabled)

    def render_page(self) -> None:
        if self.document is None:
            return
        page = self.document.load_page(self.current_page)
        if self.fit_width_enabled:
            available = max(320, self.scroll_area.viewport().width() - 34)
            self.zoom = max(0.25, min(4.0, available / page.rect.width))
        pixmap = page.get_pixmap(matrix=fitz.Matrix(self.zoom, self.zoom), alpha=False)
        image = QImage(
            pixmap.samples, pixmap.width, pixmap.height, pixmap.stride,
            QImage.Format.Format_RGB888,
        ).copy()
        self.preview_label.setPixmap(QPixmap.fromImage(image))
        self.preview_label.setFixedSize(image.size())
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

    def change_zoom(self, delta: float) -> None:
        if self.document is None:
            return
        self.fit_width_enabled = False
        self.zoom = max(0.25, min(4.0, self.zoom + delta))
        self.render_page()

    def fit_to_width(self) -> None:
        if self.document is not None:
            self.fit_width_enabled = True
            self.render_page()

    def eventFilter(self, watched, event):
        if watched is self.scroll_area.viewport() and self.fit_width_enabled and self.document is not None:
            if event.type() == QEvent.Type.Resize:
                self.render_page()
        return super().eventFilter(watched, event)

    def open_current_file(self) -> None:
        if self.current_path is None:
            return
        opened, diagnostic = open_file_native(self.current_path)
        if not opened:
            QMessageBox.warning(self, "No se pudo abrir", diagnostic)

    def open_current_folder(self) -> None:
        if self.current_path is None:
            return
        opened, diagnostic = open_directory_native(self.current_path.parent)
        if not opened:
            QMessageBox.warning(self, "No se pudo abrir la carpeta", diagnostic)

    def closeEvent(self, event) -> None:
        self.close_document()
        super().closeEvent(event)
