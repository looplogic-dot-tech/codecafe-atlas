from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from PySide6.QtCore import QProcess
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .paths import data_dir
from .platform_open import open_directory_native
from .ui_helpers import page_header


TOOLS = (
    (
        "dependency_pdf_separator",
        "Separador de PDFs por dependencia",
        "Detecta y permite corregir números de serie, consulta la base de Atlas y separa cientos de páginas en carpetas por dependencia.",
    ),
    (
        "data_bridge",
        "Atlas Data Bridge",
        "Analiza e importa hojas de cálculo hacia Atlas mediante la herramienta independiente validada.",
    ),
    (
        "spreadsheet_comparator",
        "Comparador de hojas de cálculo",
        "Compara archivos de hojas de cálculo mediante la herramienta independiente correspondiente.",
    ),
)


class AuxiliaryToolsPage(QWidget):
    """Central launcher for occasional tools whose engines remain independent."""

    def __init__(self):
        super().__init__()
        self.settings_path = data_dir() / "auxiliary_tools_settings.json"
        self.settings = self._load_settings()
        self.path_edits: dict[str, QLineEdit] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 28)
        root.setSpacing(14)
        root.addWidget(page_header(
            "Herramientas auxiliares",
            "Centraliza utilidades de uso ocasional sin acoplarlas al núcleo estable de Atlas.",
        ))

        note = QLabel(
            "Selecciona la copia real de cada herramienta que utilizas. Atlas recordará "
            "la ruta y la ejecutará en una ventana independiente."
        )
        note.setWordWrap(True)
        note.setObjectName("nativeNote")
        root.addWidget(note)

        for key, title, description in TOOLS:
            panel = QFrame()
            panel.setObjectName("nativePanel")
            panel_layout = QVBoxLayout(panel)
            heading = QLabel(title)
            heading.setObjectName("nativeSectionTitle")
            panel_layout.addWidget(heading)
            detail = QLabel(description)
            detail.setWordWrap(True)
            detail.setObjectName("pageSubtitle")
            panel_layout.addWidget(detail)

            row = QHBoxLayout()
            path_edit = QLineEdit(str(self.settings.get(key) or ""))
            path_edit.setReadOnly(True)
            path_edit.setPlaceholderText("Herramienta no configurada")
            self.path_edits[key] = path_edit
            row.addWidget(path_edit, 1)
            choose_button = QPushButton("Seleccionar…")
            choose_button.clicked.connect(lambda checked=False, tool_key=key: self.choose_tool(tool_key))
            row.addWidget(choose_button)
            open_folder_button = QPushButton("Abrir carpeta")
            open_folder_button.clicked.connect(lambda checked=False, tool_key=key: self.open_tool_folder(tool_key))
            row.addWidget(open_folder_button)
            launch_button = QPushButton("Ejecutar")
            launch_button.setObjectName("primaryButton")
            launch_button.clicked.connect(lambda checked=False, tool_key=key: self.launch_tool(tool_key))
            row.addWidget(launch_button)
            panel_layout.addLayout(row)
            root.addWidget(panel)
        root.addStretch(1)

    def _load_settings(self) -> dict[str, str]:
        try:
            payload = json.loads(self.settings_path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
        except (OSError, ValueError, TypeError):
            return {}

    def _save_settings(self) -> None:
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.settings_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(self.settings, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.settings_path)

    def choose_tool(self, key: str) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "Seleccionar herramienta",
            str(Path(str(self.settings.get(key) or "")).parent) if self.settings.get(key) else "",
            "Aplicaciones y scripts (*.exe *.bat *.cmd *.py *.sh *.AppImage);;Todos los archivos (*)",
        )
        if not selected:
            return
        path = Path(selected)
        self.settings[key] = str(path)
        self.path_edits[key].setText(str(path))
        self._save_settings()

    def launch_tool(self, key: str) -> None:
        path = Path(str(self.settings.get(key) or ""))
        if not path.is_file():
            QMessageBox.warning(
                self,
                "Herramienta no disponible",
                "Selecciona primero el archivo real de la herramienta independiente.",
            )
            return
        suffix = path.suffix.casefold()
        tool_arguments = (
            ["--database", str(data_dir() / "atlas.db")]
            if key == "dependency_pdf_separator"
            else []
        )
        if suffix == ".py":
            program, arguments = sys.executable, [str(path), *tool_arguments]
        elif suffix == ".sh":
            program, arguments = "/bin/bash", [str(path), *tool_arguments]
        elif suffix in {".bat", ".cmd"} and os.name == "nt":
            program, arguments = os.environ.get("COMSPEC", "cmd.exe"), [
                "/c", str(path), *tool_arguments
            ]
        else:
            program, arguments = str(path), tool_arguments
        started, _ = QProcess.startDetached(program, arguments, str(path.parent))
        if not started:
            QMessageBox.warning(self, "No se pudo ejecutar", str(path))

    def open_tool_folder(self, key: str) -> None:
        path = Path(str(self.settings.get(key) or ""))
        folder = path.parent if path.is_file() else path
        if not folder.is_dir():
            QMessageBox.warning(self, "Ruta no disponible", "La herramienta todavía no está configurada.")
            return
        opened, diagnostic = open_directory_native(folder)
        if not opened:
            QMessageBox.warning(self, "No se pudo abrir la carpeta", diagnostic)
