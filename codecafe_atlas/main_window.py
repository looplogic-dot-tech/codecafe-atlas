from __future__ import annotations

import sys

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QAction, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QListWidget,
    QListWidgetItem,
    QLabel,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .counter_registry_page import CounterRegistryPage
from .counter_inserter_page import CounterInserterPage
from .database import Database
from .data_page import DataPage
from .directory_page import DirectoryPage
from .formats_page import FormatsPage
from .home_page import HomePage
from .inventory_page import InventoryPage
from .paths import APP_NAME, asset_path, backups_dir, database_migration_message, database_path
from .identity import (
    APPLICATION_ID, AUTHOR_NAME, BRAND_NAME, CONTACT_EMAIL,
    ORIGIN_ID, ORIGINAL_YEAR, PRODUCT_DESCRIPTION, PRODUCT_NAME,
)
from .pdf_page import PdfPage
from .pdf_library_page import PdfLibraryPage
from .service_order_page import ServiceOrderPage
from .sync_compare_page import SyncComparePage
from .update_dialog import UpdateDialog
from . import __version__


STYLE = """
QWidget#nativeModuleBackground {
    background: #f3f6fa;
}
QLabel#nativeModuleTitle {
    color: #172033;
    font-size: 26pt;
    font-weight: 800;
    background: transparent;
}
QLabel#nativeModuleSubtitle {
    color: #667085;
    background: transparent;
    font-size: 10.5pt;
}
QFrame#nativePanel {
    background: #ffffff;
    border: 1px solid #d8dee9;
    border-radius: 14px;
}
QFrame#nativeDropZone {
    background: #eef4ff;
    border: 2px dashed #9eb4db;
    border-radius: 13px;
}
QFrame#nativeDropZone[dragActive="true"] {
    background: #e2edff;
    border-color: #185adb;
}
QLabel#dropTitle {
    color: #172033;
    font-size: 12pt;
    font-weight: 800;
    background: transparent;
}
QLabel#dropSubtitle {
    color: #667085;
    background: transparent;
}
QPushButton#secondaryButton {
    background: #eef4ff;
    color: #185adb;
    border: 1px solid #cad8ee;
}
QPushButton#secondaryButton:hover {
    background: #e2edff;
}
QLabel#nativeBadge {
    background: #e7f6ed;
    color: #147d4b;
    border-radius: 10px;
    padding: 5px 10px;
    font-weight: 700;
}
QLabel#nativeNote {
    background: #fff7e8;
    color: #8a4d00;
    border: 1px solid #f0d49f;
    border-radius: 9px;
    padding: 10px 12px;
}
QLabel#progressPercent {
    color: #344054;
    font-weight: 800;
}
QProgressBar {
    background: #e8edf3;
    border: none;
    border-radius: 5px;
    min-height: 9px;
    max-height: 9px;
}
QProgressBar::chunk {
    background: #185adb;
    border-radius: 5px;
}
QFrame#metricCard {
    background: #f8fafc;
    border: 1px solid #e1e7ef;
    border-radius: 11px;
}
QLabel#metricValue {
    color: #172033;
    font-size: 21pt;
    font-weight: 800;
    background: transparent;
}
QLabel#metricLabel {
    color: #667085;
    background: transparent;
}
QLabel#nativeSectionTitle {
    color: #172033;
    font-size: 15pt;
    font-weight: 800;
    background: transparent;
}
QLabel#nativeNotice {
    background: #e7f6ed;
    color: #147d4b;
    border: 1px solid #b9dfc8;
    border-radius: 9px;
    padding: 10px 12px;
}
QLabel#nativeNotice[error="true"] {
    background: #fff1f0;
    color: #b42318;
    border-color: #f3c9c4;
}

QPushButton#duplicateReviewButton {
    background: #fff7e8;
    color: #9a5a00;
    border: 1px solid #e8bd72;
}
QPushButton#duplicateReviewButton:hover {
    background: #ffefcf;
}
QPushButton#duplicateReviewButton:disabled {
    background: #f2f4f7;
    color: #98a2b3;
    border-color: #e4e7ec;
}
QLineEdit#tableSerialEditor[duplicate="true"] {
    background: #fff7e8;
    color: #8a4d00;
    border: 2px solid #e8a73f;
}
QLineEdit#tableSerialEditor, QLineEdit#serialEditor {
    font-family: monospace;
    font-weight: 800;
    text-transform: uppercase;
}
QPushButton#trashButton {
    background: #fff1f0;
    color: #b42318;
    border: 1px solid #f3c9c4;
    padding: 6px 9px;
}
QLabel#methodText {
    background: #e7f6ed;
    color: #147d4b;
    border-radius: 9px;
    padding: 4px 8px;
    font-weight: 700;
}
QLabel#methodOcr {
    background: #eef4ff;
    color: #185adb;
    border-radius: 9px;
    padding: 4px 8px;
    font-weight: 700;
}
QLabel#methodNone {
    background: #fff1f0;
    color: #b42318;
    border-radius: 9px;
    padding: 4px 8px;
    font-weight: 700;
}
QFrame#reviewSidebar {
    min-width: 330px;
    max-width: 360px;
    background: #ffffff;
    border-left: 1px solid #d8dee9;
}
QLabel#reviewHelp {
    background: #f7f9fc;
    color: #667085;
    border-radius: 9px;
    padding: 11px;
}
QLabel#detectedText {
    background: #fafbfc;
    color: #475467;
    border: 1px solid #d8dee9;
    border-radius: 9px;
    padding: 10px;
}

QMainWindow, QWidget {
    background: #f4f6f9;
    color: #172033;
    font-family: "Segoe UI", "Noto Sans", sans-serif;
    font-size: 10.5pt;
}
QWidget#navigationPanel {
    background: #071225;
}
QLabel#navigationLogo {
    background: #071225;
    border: none;
}
QListWidget {
    background: #14213d;
    color: #ffffff;
    border: none;
    padding: 12px 8px;
    outline: none;
}
QListWidget::item {
    padding: 13px 12px;
    border-radius: 8px;
    margin: 3px 0;
}
QListWidget::item:selected {
    background: #245fce;
}
QListWidget::item:hover:!selected {
    background: #20335d;
}
QLineEdit, QTextEdit, QComboBox {
    background: #ffffff;
    border: 1px solid #bfc7d4;
    border-radius: 7px;
    padding: 7px 9px;
    selection-background-color: #245fce;
}
QLineEdit:focus, QTextEdit:focus, QComboBox:focus {
    border: 2px solid #245fce;
}
QPushButton {
    background: #e7ebf2;
    border: none;
    border-radius: 8px;
    padding: 9px 13px;
    font-weight: 600;
}
QPushButton:hover {
    background: #d9e0eb;
}
QPushButton#primaryButton {
    background: #185adb;
    color: white;
}
QPushButton#primaryButton:hover {
    background: #0d43ae;
}
QPushButton#dangerButton {
    background: #fee4e2;
    color: #b42318;
}
QPushButton#homeCard {
    background: #ffffff;
    border: 1px solid #d8dee9;
    text-align: left;
    padding: 20px;
    font-size: 12pt;
}
QPushButton#homeCard:hover {
    border: 2px solid #185adb;
    background: #f8fbff;
}
QGroupBox {
    background: #ffffff;
    border: 1px solid #d8dee9;
    border-radius: 10px;
    margin-top: 12px;
    padding: 12px;
    font-weight: 700;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 5px;
}
QTableWidget {
    background: #ffffff;
    alternate-background-color: #f8fafc;
    border: 1px solid #d8dee9;
    border-radius: 9px;
    gridline-color: #e5e9f0;
}
QHeaderView::section {
    background: #e9edf4;
    border: none;
    border-right: 1px solid #d8dee9;
    padding: 8px;
    font-weight: 700;
}

QListWidget#pdfLibraryList {
    background: #ffffff;
    color: #172033;
    border: 1px solid #d8dee9;
    border-radius: 9px;
    padding: 6px;
}
QListWidget#pdfLibraryList::item {
    padding: 10px 8px;
    border-radius: 7px;
    margin: 2px 0;
}
QListWidget#pdfLibraryList::item:selected {
    background: #e2edff;
    color: #174b8f;
}
QListWidget#pdfLibraryList::item:hover:!selected {
    background: #f3f6fa;
}
QLabel#pdfViewerCanvas {
    background: #e9edf3;
    color: #667085;
    border: none;
}

QFrame#dialogFooter {
    background: #f8fafc;
    border-top: 1px solid #d8dee9;
}
QLabel#pageTitle {
    font-size: 22pt;
    font-weight: 800;
}
QLabel#pageSubtitle {
    color: #667085;
}

QFrame#directoryHero {
    background: #173b6d;
    border: none;
}
QLabel#directoryTitle {
    background: transparent;
    border: none;
    color: #ffffff;
    font-size: 24pt;
    font-weight: 800;
    padding: 0;
}
QLabel#directorySubtitle {
    background: transparent;
    border: none;
    color: #e7effb;
    font-size: 11pt;
    padding: 0;
}
QFrame#directoryPanel, QFrame#directoryStats {
    background: white;
    border: 1px solid #d9e1ec;
    border-radius: 12px;
}
QFrame#buildingCard {
    background: white;
    border: 1px solid #d9e1ec;
    border-radius: 12px;
}
QFrame#buildingHeader {
    background: #edf4ff;
    border-top-left-radius: 11px;
    border-top-right-radius: 11px;
    border-bottom: 1px solid #d9e1ec;
}
QLabel#buildingTitle {
    color: #173b6d;
    font-size: 13pt;
    font-weight: 800;
}
QLabel#buildingAddress {
    color: #667085;
}
QLabel#directoryColumn {
    color: #475467;
    font-size: 9pt;
    font-weight: 800;
}
QFrame#directoryRow {
    background: white;
    border-top: 1px solid #e9edf3;
}
QFrame#directoryRow:hover {
    background: #fbfdff;
}
QLabel#floorBadge {
    background: #eef2f6;
    color: #344054;
    border-radius: 10px;
    padding: 4px 8px;
}
QPushButton#departmentLink {
    background: transparent;
    color: #174b8f;
    border: none;
    padding: 0;
    text-align: left;
    font-weight: 750;
}
QPushButton#departmentLink:hover {
    color: #185abd;
    text-decoration: underline;
}
QPushButton#softButton {
    background: #eaf1fb;
    color: #174b8f;
}

QFrame#buildingHeader:hover {
    background: #e2edff;
}
QPushButton#equipmentToggle {
    background: #f6f8fb;
    color: #344054;
    border: 1px solid #d9e1ec;
    border-radius: 8px;
    padding: 7px 10px;
    text-align: left;
    font-weight: 700;
}
QPushButton#equipmentToggle:hover {
    background: #eef4ff;
    color: #174b8f;
}
QFrame#equipmentPanel {
    background: #fbfcfe;
    border: 1px solid #e4e9f1;
    border-radius: 8px;
}
QFrame#equipmentItem {
    background: white;
    border: 1px solid #e4e9f1;
    border-radius: 7px;
}
QLabel#equipmentName {
    color: #173b6d;
    font-weight: 750;
}
QLabel#counterValue {
    color: #176b45;
    font-weight: 700;
}
QLabel#statText {
    color: #344054;
    font-weight: 700;
}
QLabel#directoryEmpty {
    color: #667085;
    background: white;
    border: 1px solid #d9e1ec;
    border-radius: 12px;
}
QLabel#dialogTitle {
    font-size: 18pt;
    font-weight: 800;
}
"""


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} — v{__version__}")
        self.setWindowIcon(QIcon(str(asset_path("codecafe_atlas_icon.png"))))
        self.resize(1440, 880)
        self.setMinimumSize(1000, 650)

        self.database = Database(database_path())
        self._close_backup_done = False

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.setCentralWidget(splitter)

        navigation_panel = QWidget()
        navigation_panel.setObjectName("navigationPanel")
        navigation_panel.setFixedWidth(230)
        navigation_layout = QVBoxLayout(navigation_panel)
        navigation_layout.setContentsMargins(8, 10, 8, 8)
        navigation_layout.setSpacing(4)

        navigation_logo = QLabel()
        navigation_logo.setObjectName("navigationLogo")
        navigation_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_pixmap = QPixmap(str(asset_path("codecafe_atlas_logo.png")))
        if not logo_pixmap.isNull():
            navigation_logo.setPixmap(logo_pixmap.scaled(
                205,
                100,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))
            navigation_logo.setAccessibleName(f"Logotipo de {PRODUCT_NAME}")
            navigation_layout.addWidget(navigation_logo)

        self.navigation = QListWidget()
        self.navigation.setObjectName("mainNavigation")
        navigation_layout.addWidget(self.navigation, 1)
        splitter.addWidget(navigation_panel)

        self.stack = QStackedWidget()
        splitter.addWidget(self.stack)
        splitter.setStretchFactor(1, 1)

        self.home_page = HomePage()
        self.pdf_page = PdfPage()
        self.pdf_library_page = PdfLibraryPage()
        self.counter_registry_page = CounterRegistryPage(self.database)
        self.counter_inserter_page = CounterInserterPage()
        self.service_order_page = ServiceOrderPage(self.database)
        self.formats_page = FormatsPage(self.database)
        self.inventory_page = InventoryPage(
            self.database,
            on_equipment_changed=self.service_order_page.full_refresh,
        )
        self.directory_page = DirectoryPage(
            self.database,
            on_dependencies_changed=self.refresh_dependency_consumers,
        )
        self.data_page = DataPage(self.database, refresh_callback=self.refresh_all_data)
        self.sync_compare_page = SyncComparePage(self.database)

        pages = [
            ("home", "Inicio", self.home_page),
            ("pdf", "Separador PDF", self.pdf_page),
            ("pdf_library", "Visor PDF", self.pdf_library_page),
            ("counters", "Registro de contadores", self.counter_registry_page),
            ("counter_inserter", "Insertador de contadores", self.counter_inserter_page),
            ("service_order", "Órdenes de servicio", self.service_order_page),
            ("formats", "Administración de formatos", self.formats_page),
            ("directory", "Directorio", self.directory_page),
            ("inventory", "Inventario", self.inventory_page),
            ("data", "Administrar datos", self.data_page),
            ("sync_compare", "Homologación DB", self.sync_compare_page),
        ]
        self.page_indexes = {}
        for key, label, widget in pages:
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, key)
            self.navigation.addItem(item)
            self.page_indexes[key] = self.stack.addWidget(widget)

        self.navigation.currentItemChanged.connect(self.change_page)
        self.home_page.open_page.connect(self.open_page)
        self.formats_page.formats_changed.connect(
            self.service_order_page.refresh_saved_formats
        )
        self.formats_page.format_requested.connect(
            self.apply_service_format
        )
        self.navigation.setCurrentRow(0)

        file_menu = self.menuBar().addMenu("Archivo")

        import_action = QAction("Cargar o migrar base existente…", self)
        import_action.triggered.connect(lambda: self.open_page("data"))

        export_excel_action = QAction("Exportar base a Excel editable…", self)
        export_excel_action.triggered.connect(self.data_page.export_editable_excel)

        backup_action = QAction("Crear respaldo ahora", self)
        backup_action.triggered.connect(self.data_page.create_backup)

        database_action = QAction("Ubicación de la base de datos", self)
        database_action.triggered.connect(self.data_page.show_database_path)

        exit_action = QAction("Salir", self)
        exit_action.triggered.connect(self.close)

        file_menu.addAction(import_action)
        file_menu.addAction(export_excel_action)
        file_menu.addAction(backup_action)
        file_menu.addSeparator()
        file_menu.addAction(database_action)
        file_menu.addSeparator()
        file_menu.addAction(exit_action)

        settings_menu = self.menuBar().addMenu("Configuración")
        dashboard_action = QAction("Personalizar dashboard…", self)
        dashboard_action.triggered.connect(
            lambda: self.home_page.customize_dashboard(self)
        )
        settings_menu.addAction(dashboard_action)

        help_menu = self.menuBar().addMenu("Ayuda")

        update_action = QAction(
            f"Actualizar {PRODUCT_NAME}…",
            self,
        )
        update_action.triggered.connect(
            self.show_update_dialog
        )

        about_action = QAction("Acerca de", self)
        about_action.triggered.connect(self.show_about)
        contact_action = QAction("Contacto", self)
        contact_action.triggered.connect(self.show_contact)

        help_menu.addAction(update_action)
        help_menu.addSeparator()
        help_menu.addAction(about_action)
        help_menu.addAction(contact_action)

        self.statusBar().showMessage(f"Base de datos: {database_path()}")
        migration_message = database_migration_message()
        if migration_message:
            QTimer.singleShot(0, lambda: QMessageBox.information(
                self, "Base de datos recuperada", migration_message
            ))

    def change_page(self, current, previous):
        if current is None:
            return

        key = current.data(Qt.ItemDataRole.UserRole)
        self.stack.setCurrentIndex(self.page_indexes[key])

        # Las pantallas mantienen su estado mientras la aplicación está abierta.
        # Solo se actualizan automáticamente los módulos ligados a la base de datos.
        if key == "inventory":
            self.inventory_page.full_refresh()
        elif key == "directory":
            self.directory_page.refresh()
        elif key == "service_order":
            self.service_order_page.full_refresh()
        elif key == "formats":
            self.formats_page.refresh()

    def apply_service_format(self, format_id: int) -> None:
        if self.service_order_page.apply_saved_format(format_id, notify=False):
            self.open_page("service_order")
            QMessageBox.information(
                self,
                "Formato precargado",
                "El formato fue aplicado a la captura de la orden de servicio.",
            )

    def open_page(self, key: str):
        for index in range(self.navigation.count()):
            item = self.navigation.item(index)
            if item.data(Qt.ItemDataRole.UserRole) == key:
                self.navigation.setCurrentRow(index)
                break

    def refresh_dependency_consumers(self):
        self.inventory_page.refresh_dependencies()
        self.service_order_page.full_refresh()

    def refresh_all_data(self):
        self.directory_page.clear_form()
        self.inventory_page.clear_form()
        self.directory_page.refresh()
        self.inventory_page.full_refresh()
        self.service_order_page.full_refresh()
        self.formats_page.refresh()

    def import_database(self):
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "Seleccionar base de datos existente",
            "",
            "Bases SQLite (*.db *.sqlite *.sqlite3);;Todos los archivos (*)",
        )
        if not selected:
            return

        try:
            info = self.database.inspect_database(selected)
        except Exception as error:
            QMessageBox.critical(self, "Base no válida", str(error))
            return

        if info["mode"] == "native":
            description = (
                f"La base usa la estructura compatible de {PRODUCT_NAME}.\n\n"
                "Se reemplazará la base actual por la seleccionada."
            )
        elif info["mode"] == "legacy":
            description = (
                "La base parece provenir del inventario anterior.\n\n"
                "Se agregarán sus ubicaciones y equipos a la base actual. "
                "Los números de serie duplicados se omitirán."
            )
        else:
            tables = ", ".join(info["tables"]) or "ninguna"
            QMessageBox.warning(
                self,
                "Estructura no reconocida",
                f"No se encontraron tablas compatibles.\n\nTablas detectadas: {tables}",
            )
            return

        counts = "\n".join(
            f"• {table}: {count} registros"
            for table, count in sorted(info["counts"].items())
        )
        answer = QMessageBox.question(
            self,
            "Confirmar importación",
            f"{description}\n\nContenido detectado:\n{counts}\n\n"
            "Antes de continuar se creará un respaldo automático.\n\n"
            "¿Continuar?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            result = self.database.import_existing_database(selected, backups_dir())
            self.refresh_all_data()
        except Exception as error:
            QMessageBox.critical(
                self,
                "La importación no se completó",
                f"{error}\n\nLa base anterior fue conservada o restaurada automáticamente.",
            )
            return

        mode_text = (
            "Base cargada completamente"
            if result["mode"] == "native"
            else "Migración terminada"
        )
        QMessageBox.information(
            self,
            mode_text,
            f"Dependencias disponibles/importadas: {result['dependencies']}\n"
            f"Equipos disponibles/importados: {result['equipment']}\n"
            f"Registros omitidos: {result['skipped']}\n\n"
            f"Respaldo anterior:\n{result['backup']}",
        )

    def create_backup(self):
        try:
            path = self.database.backup(backups_dir())
        except Exception as error:
            QMessageBox.critical(self, "No se pudo respaldar", str(error))
            return
        QMessageBox.information(
            self,
            "Respaldo creado",
            f"La base se respaldó correctamente en:\n\n{path}",
        )

    def _show_close_notice(
        self,
        title: str,
        message: str,
        icon: QMessageBox.Icon = QMessageBox.Icon.Information,
        timeout_ms: int = 1400,
    ) -> None:
        notice = QMessageBox(self)
        notice.setIcon(icon)
        notice.setWindowTitle(title)
        notice.setText(message)
        notice.setStandardButtons(QMessageBox.StandardButton.NoButton)
        QTimer.singleShot(timeout_ms, notice.accept)
        notice.exec()

    def closeEvent(self, event) -> None:
        if self._close_backup_done:
            event.accept()
            return

        self._close_backup_done = True
        try:
            path = self.database.backup(backups_dir())
        except Exception as error:
            self._show_close_notice(
                "Respaldo no realizado",
                f"No fue posible crear el respaldo automático:\n\n{error}",
                icon=QMessageBox.Icon.Warning,
                timeout_ms=3500,
            )
        else:
            self._show_close_notice(
                "Respaldo realizado",
                f"La base de datos se respaldó correctamente antes de cerrar.\n\n{path}",
            )

        event.accept()

    def show_database_path(self):
        QMessageBox.information(
            self,
            "Base de datos portátil",
            f"La base de datos se guarda en:\n\n{database_path()}"
        )

    def show_update_dialog(self):
        dialog = UpdateDialog(__version__, self)
        dialog.exec()

    def show_about(self):
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Acerca de {PRODUCT_NAME}")
        dialog.setWindowIcon(QIcon(str(asset_path("codecafe_atlas_icon.png"))))
        dialog.setMinimumWidth(660)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(26, 22, 26, 20)
        layout.setSpacing(14)

        logo_label = QLabel()
        logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_pixmap = QPixmap(str(asset_path("codecafe_atlas_logo.png")))
        if not logo_pixmap.isNull():
            logo_label.setPixmap(logo_pixmap.scaled(
                580,
                255,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))
            logo_label.setAccessibleName(f"Logotipo de {PRODUCT_NAME}")
            layout.addWidget(logo_label)

        details = QLabel(
            f"<b>{PRODUCT_NAME} v{__version__}</b><br>"
            f"{PRODUCT_DESCRIPTION}<br><br>"
            "Concepto original, arquitectura y desarrollo de software por<br>"
            f"<b>{AUTHOR_NAME}</b><br><br>"
            f"{BRAND_NAME}<br>"
            f"{CONTACT_EMAIL}<br><br>"
            f"Desarrollado originalmente en {ORIGINAL_YEAR}.<br>"
            f"Application ID: {APPLICATION_ID}<br>"
            f"Origin ID: {ORIGIN_ID}"
        )
        details.setAlignment(Qt.AlignmentFlag.AlignCenter)
        details.setTextFormat(Qt.TextFormat.RichText)
        details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(details)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    def show_contact(self):
        QMessageBox.information(
            self,
            "Contacto",
            f"{AUTHOR_NAME}\n\n"
            f"{CONTACT_EMAIL}"
        )


def run() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(BRAND_NAME)
    app.setOrganizationDomain("codecafe.io")
    app.setApplicationDisplayName(PRODUCT_NAME)
    app.setWindowIcon(QIcon(str(asset_path("codecafe_atlas_icon.png"))))
    app.setProperty("applicationId", APPLICATION_ID)
    app.setProperty("originId", ORIGIN_ID)
    app.setStyleSheet(STYLE)
    window = MainWindow()
    window.show()
    return app.exec()
