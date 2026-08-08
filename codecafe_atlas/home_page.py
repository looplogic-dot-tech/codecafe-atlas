from __future__ import annotations

import json
import shutil
from pathlib import Path

from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from .paths import dashboard_dir
from .identity import PRODUCT_NAME
from .ui_helpers import page_header


DEFAULT_SETTINGS = {
    "background_path": "",
    "background_mode": "fill",
    "background_opacity": 25,
}
MODE_LABELS = {
    "fill": "Rellenar",
    "fit": "Ajustar",
    "center": "Centrar",
    "tile": "Mosaico",
}


def _settings_path() -> Path:
    return dashboard_dir() / "settings.json"


def load_dashboard_settings() -> dict:
    settings = dict(DEFAULT_SETTINGS)
    path = _settings_path()
    if path.is_file():
        try:
            saved = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(saved, dict):
                settings.update(saved)
        except (OSError, ValueError, TypeError):
            pass
    return settings


def save_dashboard_settings(settings: dict) -> None:
    _settings_path().write_text(
        json.dumps(settings, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


class DashboardCustomizationDialog(QDialog):
    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Personalizar dashboard")
        self.setMinimumWidth(560)
        self.settings = dict(settings)
        self.selected_source = ""

        layout = QVBoxLayout(self)
        title = QLabel("Fondo del dashboard")
        title.setObjectName("dialogTitle")
        layout.addWidget(title)

        description = QLabel(
            f"Selecciona una imagen local. {PRODUCT_NAME} guardará una copia para "
            "que el fondo continúe disponible aunque se mueva el archivo original."
        )
        description.setWordWrap(True)
        description.setObjectName("pageSubtitle")
        layout.addWidget(description)

        image_row = QHBoxLayout()
        self.path_label = QLabel(self._display_path())
        self.path_label.setWordWrap(True)
        self.path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        choose_button = QPushButton("Seleccionar imagen…")
        choose_button.clicked.connect(self.choose_image)
        image_row.addWidget(self.path_label, 1)
        image_row.addWidget(choose_button)
        layout.addLayout(image_row)

        form = QFormLayout()
        self.mode_combo = QComboBox()
        for key, label in MODE_LABELS.items():
            self.mode_combo.addItem(label, key)
        mode_index = self.mode_combo.findData(self.settings.get("background_mode", "fill"))
        self.mode_combo.setCurrentIndex(max(0, mode_index))
        form.addRow("Modo de visualización:", self.mode_combo)

        opacity_row = QHBoxLayout()
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(0, 100)
        self.opacity_slider.setValue(int(self.settings.get("background_opacity", 25)))
        self.opacity_value = QLabel(f"{self.opacity_slider.value()} %")
        self.opacity_slider.valueChanged.connect(
            lambda value: self.opacity_value.setText(f"{value} %")
        )
        opacity_row.addWidget(self.opacity_slider, 1)
        opacity_row.addWidget(self.opacity_value)
        form.addRow("Opacidad de la imagen:", opacity_row)
        layout.addLayout(form)

        restore_button = QPushButton("Restaurar fondo predeterminado")
        restore_button.clicked.connect(self.restore_default)
        layout.addWidget(restore_button, alignment=Qt.AlignmentFlag.AlignLeft)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _display_path(self) -> str:
        path = self.selected_source or str(self.settings.get("background_path", ""))
        if path and not Path(path).is_absolute():
            path = str(dashboard_dir() / path)
        return path if path else "Fondo predeterminado"

    def choose_image(self):
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "Seleccionar imagen para el dashboard",
            "",
            "Imágenes (*.png *.jpg *.jpeg *.webp);;Todos los archivos (*)",
        )
        if selected:
            self.selected_source = selected
            self.path_label.setText(selected)

    def restore_default(self):
        self.selected_source = ""
        self.settings["background_path"] = ""
        self.path_label.setText("Fondo predeterminado")

    def result_settings(self) -> dict:
        result = dict(self.settings)
        result["background_mode"] = str(self.mode_combo.currentData())
        result["background_opacity"] = self.opacity_slider.value()

        if self.selected_source:
            source = Path(self.selected_source)
            suffix = source.suffix.lower() if source.suffix else ".png"
            destination = dashboard_dir() / f"background{suffix}"
            for old in dashboard_dir().glob("background.*"):
                if old != destination:
                    try:
                        old.unlink()
                    except OSError:
                        pass
            shutil.copy2(source, destination)
            result["background_path"] = destination.name
        elif not self.settings.get("background_path"):
            result["background_path"] = ""

        return result


class HomePage(QWidget):
    open_page = Signal(str)

    def __init__(self):
        super().__init__()
        self.settings = load_dashboard_settings()
        self.background = QPixmap()
        self._reload_background()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 28)
        layout.addWidget(page_header(
            PRODUCT_NAME,
            "Plataforma modular para documentos, contadores, directorio e inventario."
        ))

        grid = QGridLayout()
        grid.setSpacing(16)
        cards = [
            ("pdf", "Separador de PDF", "Analiza páginas, revisa números de serie y exporta los documentos."),
            ("counters", "Registro de contadores", "Escanea reportes, extrae contadores y genera archivos Excel."),
            ("pdf_library", "Visor PDF", "Indexa carpetas, busca documentos y consulta archivos en un visor local."),
            ("service_order", "Órdenes de servicio", "Genera cédulas desde la plantilla y registra cada folio."),
            ("formats", "Administración de formatos", "Crea formatos reutilizables y precarga órdenes de servicio."),
            ("directory", "Directorio de juzgados", "Administra edificios, pisos, dependencias, oficinas y CTA."),
            ("inventory", "Inventario de equipos", "Registra impresoras, escáneres y otros equipos por dependencia."),
            ("data", "Administrar datos", "Carga una base existente y crea respaldos de seguridad."),
        ]

        for index, (page, title, description) in enumerate(cards):
            button = QPushButton(f"{title}\n\n{description}")
            button.setObjectName("homeCard")
            button.setMinimumHeight(150)
            button.clicked.connect(lambda checked=False, page=page: self.open_page.emit(page))
            grid.addWidget(button, index // 2, index % 2)

        layout.addLayout(grid)
        layout.addStretch(1)

        note = QLabel(
            "La personalización del dashboard se guarda localmente en este equipo."
        )
        note.setObjectName("pageSubtitle")
        note.setWordWrap(True)
        layout.addWidget(note)

    def _reload_background(self):
        path = Path(str(self.settings.get("background_path", "")))
        if path and not path.is_absolute():
            path = dashboard_dir() / path
        self.background = QPixmap(str(path)) if path.is_file() else QPixmap()
        self.update()

    def customize_dashboard(self, parent=None):
        dialog = DashboardCustomizationDialog(self.settings, parent or self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            self.settings = dialog.result_settings()
            save_dashboard_settings(self.settings)
            self._reload_background()
        except OSError as error:
            QMessageBox.critical(
                parent or self,
                "No se pudo guardar el fondo",
                str(error),
            )

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.GlobalColor.white)

        if not self.background.isNull():
            painter.save()
            painter.setOpacity(max(0.0, min(1.0, int(self.settings.get("background_opacity", 25)) / 100)))
            mode = str(self.settings.get("background_mode", "fill"))
            area = self.rect()

            if mode == "tile":
                painter.drawTiledPixmap(area, self.background)
            elif mode == "center":
                x = (area.width() - self.background.width()) // 2
                y = (area.height() - self.background.height()) // 2
                painter.drawPixmap(x, y, self.background)
            else:
                aspect = (
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding
                    if mode == "fill"
                    else Qt.AspectRatioMode.KeepAspectRatio
                )
                scaled = self.background.scaled(
                    area.size(), aspect, Qt.TransformationMode.SmoothTransformation
                )
                x = (area.width() - scaled.width()) // 2
                y = (area.height() - scaled.height()) // 2
                painter.drawPixmap(QRect(x, y, scaled.width(), scaled.height()), scaled)
            painter.restore()

        super().paintEvent(event)
