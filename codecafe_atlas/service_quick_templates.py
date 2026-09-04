from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)


DEFAULT_QUICK_TEMPLATES = {
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


def load_quick_templates(path: Path) -> dict[str, str]:
    """Load user-managed templates; seed the historical defaults once."""
    path = Path(path)
    if not path.exists():
        templates = dict(DEFAULT_QUICK_TEMPLATES)
        save_quick_templates(path, templates)
        return templates
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return {
        str(name).strip(): str(text or "")
        for name, text in payload.items()
        if str(name).strip() and str(name).strip().casefold() != "entrada manual"
    }


def save_quick_templates(path: Path, templates: dict[str, str]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = {
        str(name).strip(): str(text or "")
        for name, text in templates.items()
        if str(name).strip() and str(name).strip().casefold() != "entrada manual"
    }
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)


class QuickTemplateEditorDialog(QDialog):
    templates_changed = Signal()

    def __init__(self, parent, settings_path: Path):
        super().__init__(parent)
        self.settings_path = Path(settings_path)
        self.templates = load_quick_templates(self.settings_path)
        self.current_name = ""

        self.setWindowTitle("Editor de plantillas rápidas")
        self.resize(820, 560)
        root = QVBoxLayout(self)

        intro = QLabel(
            "Crea, modifica o elimina textos reutilizables para Falla reportada. "
            "Entrada manual permanece disponible y no es una plantilla eliminable."
        )
        intro.setWordWrap(True)
        root.addWidget(intro)

        body = QHBoxLayout()
        self.list_widget = QListWidget()
        self.list_widget.currentItemChanged.connect(self.load_selected)
        body.addWidget(self.list_widget, 1)

        editor = QVBoxLayout()
        editor.addWidget(QLabel("Nombre"))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Nombre de la plantilla")
        editor.addWidget(self.name_edit)
        editor.addWidget(QLabel("Texto para Falla reportada"))
        self.text_edit = QTextEdit()
        self.text_edit.setPlaceholderText("Escribe el texto reutilizable")
        editor.addWidget(self.text_edit, 1)

        buttons = QHBoxLayout()
        new_button = QPushButton("Nueva")
        save_button = QPushButton("Guardar")
        save_button.setObjectName("primaryButton")
        delete_button = QPushButton("Eliminar")
        delete_button.setObjectName("dangerButton")
        close_button = QPushButton("Cerrar")
        buttons.addWidget(new_button)
        buttons.addWidget(save_button)
        buttons.addWidget(delete_button)
        buttons.addStretch(1)
        buttons.addWidget(close_button)
        editor.addLayout(buttons)
        body.addLayout(editor, 2)
        root.addLayout(body, 1)

        new_button.clicked.connect(self.new_template)
        save_button.clicked.connect(self.save_current)
        delete_button.clicked.connect(self.delete_current)
        close_button.clicked.connect(self.accept)
        self.refresh_list()

    def refresh_list(self, select_name: str = "") -> None:
        self.list_widget.clear()
        for name in sorted(self.templates, key=str.casefold):
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, name)
            self.list_widget.addItem(item)
            if name == select_name:
                self.list_widget.setCurrentItem(item)
        if self.list_widget.currentRow() < 0 and self.list_widget.count():
            self.list_widget.setCurrentRow(0)

    def load_selected(self, current: QListWidgetItem | None, previous) -> None:
        del previous
        if current is None:
            return
        self.current_name = str(current.data(Qt.ItemDataRole.UserRole) or "")
        self.name_edit.setText(self.current_name)
        self.text_edit.setPlainText(self.templates.get(self.current_name, ""))

    def new_template(self) -> None:
        self.list_widget.clearSelection()
        self.list_widget.setCurrentRow(-1)
        self.current_name = ""
        self.name_edit.clear()
        self.text_edit.clear()
        self.name_edit.setFocus()

    def save_current(self) -> None:
        name = self.name_edit.text().strip()
        text = self.text_edit.toPlainText().strip()
        if not name:
            QMessageBox.warning(self, "Nombre obligatorio", "Escribe un nombre para la plantilla.")
            return
        if name.casefold() == "entrada manual":
            QMessageBox.warning(self, "Nombre reservado", "Entrada manual es un modo permanente de captura.")
            return
        if not text:
            QMessageBox.warning(self, "Texto obligatorio", "Escribe el texto de la plantilla.")
            return
        existing = next((item for item in self.templates if item.casefold() == name.casefold()), None)
        if existing is not None and existing != self.current_name:
            QMessageBox.warning(self, "Nombre repetido", f"Ya existe una plantilla llamada «{existing}».")
            return
        if self.current_name and self.current_name != name:
            self.templates.pop(self.current_name, None)
        self.templates[name] = text
        save_quick_templates(self.settings_path, self.templates)
        self.current_name = name
        self.refresh_list(name)
        self.templates_changed.emit()

    def delete_current(self) -> None:
        name = self.current_name
        if not name or name not in self.templates:
            return
        answer = QMessageBox.question(
            self,
            "Eliminar plantilla rápida",
            f"¿Eliminar permanentemente la plantilla «{name}»?\n\n"
            "Las órdenes ya guardadas conservarán su texto.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.templates.pop(name, None)
        save_quick_templates(self.settings_path, self.templates)
        self.current_name = ""
        self.name_edit.clear()
        self.text_edit.clear()
        self.refresh_list()
        self.templates_changed.emit()
