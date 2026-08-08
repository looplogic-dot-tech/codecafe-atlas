from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from .identity import PRODUCT_NAME, PRODUCT_SLUG
from .updater import (
    UpdatePackageError,
    inspect_update_package,
    launch_external_updater,
)


class UpdateDialog(QDialog):
    def __init__(self, current_version: str, parent=None):
        super().__init__(parent)
        self.current_version = current_version
        self.package_info = None

        self.setWindowTitle(f"Actualizar {PRODUCT_NAME}")
        self.setModal(True)
        self.resize(720, 520)
        self.setMinimumSize(620, 450)

        root = QVBoxLayout(self)

        title = QLabel(f"Actualizar {PRODUCT_NAME}")
        title.setObjectName("dialogTitle")
        subtitle = QLabel(
            "Selecciona un paquete de actualización oficial. "
            "La aplicación validará la versión, plataforma y todos los archivos "
            "antes de cerrar e iniciar el actualizador externo."
        )
        subtitle.setObjectName("pageSubtitle")
        subtitle.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(subtitle)

        version_box = QFrame()
        version_box.setObjectName("nativePanel")
        version_layout = QFormLayout(version_box)
        version_layout.addRow(
            "Versión instalada",
            QLabel(current_version),
        )
        self.package_version = QLabel("Ningún paquete seleccionado")
        version_layout.addRow(
            "Versión disponible",
            self.package_version,
        )
        root.addWidget(version_box)

        package_row = QHBoxLayout()
        self.package_path = QLineEdit()
        self.package_path.setReadOnly(True)
        self.package_path.setPlaceholderText(
            f"Selecciona {PRODUCT_SLUG}-update-....zip"
        )
        browse_button = QPushButton("Examinar…")
        browse_button.clicked.connect(self.choose_package)
        package_row.addWidget(self.package_path, 1)
        package_row.addWidget(browse_button)
        root.addLayout(package_row)

        self.status = QLabel(
            "Todavía no se ha validado ningún paquete."
        )
        self.status.setObjectName("nativeNote")
        self.status.setWordWrap(True)
        root.addWidget(self.status)

        notes_label = QLabel("Notas de la versión")
        notes_label.setStyleSheet("font-weight: 700;")
        root.addWidget(notes_label)

        self.release_notes = QTextEdit()
        self.release_notes.setReadOnly(True)
        self.release_notes.setPlaceholderText(
            "Las notas incluidas en el paquete aparecerán aquí."
        )
        root.addWidget(self.release_notes, 1)

        warning = QLabel(
            f"Durante la actualización se cerrará {PRODUCT_NAME}. "
            "El actualizador conservará las carpetas data y backups, "
            "creará una copia de la instalación anterior y abrirá la nueva versión."
        )
        warning.setObjectName("nativeNote")
        warning.setWordWrap(True)
        root.addWidget(warning)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel
        )
        self.install_button = QPushButton(
            "Cerrar e instalar actualización"
        )
        self.install_button.setObjectName("primaryButton")
        self.install_button.setEnabled(False)
        buttons.addButton(
            self.install_button,
            QDialogButtonBox.ButtonRole.AcceptRole,
        )
        buttons.rejected.connect(self.reject)
        self.install_button.clicked.connect(self.install_update)
        root.addWidget(buttons)

    def choose_package(self):
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "Seleccionar paquete de actualización",
            str(Path.home()),
            f"Actualizaciones de {PRODUCT_NAME} (*.zip)",
        )
        if not selected:
            return

        self.package_path.setText(selected)
        self.validate_package(selected)

    def validate_package(self, selected: str):
        self.package_info = None
        self.install_button.setEnabled(False)

        try:
            info = inspect_update_package(
                selected,
                self.current_version,
                require_newer=True,
            )
        except UpdatePackageError as error:
            self.package_version.setText("Paquete no válido")
            self.status.setText(str(error))
            self.status.setProperty("error", True)
            self.status.style().unpolish(self.status)
            self.status.style().polish(self.status)
            self.release_notes.clear()
            return

        self.package_info = info
        self.package_version.setText(info.version)
        size_mb = info.total_size / (1024 * 1024)
        self.status.setText(
            f"Paquete válido para {info.platform_name} / "
            f"{info.architecture}. "
            f"{info.file_count} archivos, {size_mb:.1f} MB."
        )
        self.status.setProperty("error", False)
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)
        self.release_notes.setPlainText(
            info.release_notes
            or "Esta versión no incluye notas adicionales."
        )
        self.install_button.setEnabled(True)

    def install_update(self):
        if self.package_info is None:
            return

        answer = QMessageBox.question(
            self,
            "Instalar actualización",
            f"Se instalará {PRODUCT_NAME} "
            f"{self.package_info.version}.\n\n"
            "Guarda cualquier trabajo pendiente antes de continuar.\n\n"
            "¿Cerrar la aplicación e iniciar el actualizador?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            launch_external_updater(
                self.package_info.package_path,
                self.current_version,
            )
        except Exception as error:
            QMessageBox.critical(
                self,
                "No se pudo iniciar el actualizador",
                str(error),
            )
            return

        self.accept()
        parent = self.parentWidget()
        if parent is not None:
            parent.close()
