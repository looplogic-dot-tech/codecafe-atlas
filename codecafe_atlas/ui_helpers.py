from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


def page_header(title: str, subtitle: str) -> QWidget:
    wrapper = QWidget()
    layout = QVBoxLayout(wrapper)
    layout.setContentsMargins(0, 0, 0, 8)
    title_label = QLabel(title)
    title_label.setObjectName("pageTitle")
    subtitle_label = QLabel(subtitle)
    subtitle_label.setWordWrap(True)
    subtitle_label.setObjectName("pageSubtitle")
    layout.addWidget(title_label)
    layout.addWidget(subtitle_label)
    return wrapper


def line_edit(placeholder: str = "") -> QLineEdit:
    widget = QLineEdit()
    widget.setPlaceholderText(placeholder)
    widget.setClearButtonEnabled(True)
    return widget


def notes_edit(placeholder: str = "") -> QTextEdit:
    widget = QTextEdit()
    widget.setPlaceholderText(placeholder)
    widget.setMaximumHeight(90)
    return widget


def standard_actions() -> tuple[QWidget, QPushButton, QPushButton, QPushButton]:
    wrapper = QWidget()
    layout = QHBoxLayout(wrapper)
    layout.setContentsMargins(0, 0, 0, 0)
    new_button = QPushButton("Nuevo / limpiar")
    save_button = QPushButton("Guardar")
    save_button.setObjectName("primaryButton")
    delete_button = QPushButton("Eliminar")
    delete_button.setObjectName("dangerButton")
    layout.addWidget(new_button)
    layout.addStretch(1)
    layout.addWidget(delete_button)
    layout.addWidget(save_button)
    return wrapper, new_button, save_button, delete_button
