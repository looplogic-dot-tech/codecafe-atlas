from __future__ import annotations
from pathlib import Path
from PySide6.QtWidgets import QFileDialog, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget
from .database import Database
from .editable_excel_export import export_editable_excel
from .paths import backups_dir, database_path
from .ui_helpers import page_header

class DataPage(QWidget):
    def __init__(self, database: Database, refresh_callback=None):
        super().__init__(); self.database=database; self.refresh_callback=refresh_callback
        layout=QVBoxLayout(self); layout.setContentsMargins(28,24,28,28)
        layout.addWidget(page_header("Administrar datos","Reemplaza, previsualiza o restablece la base con respaldo automático."))
        self.current_path=QLabel(f"Base activa:\n{database_path()}"); self.current_path.setWordWrap(True); self.current_path.setObjectName("dataPath"); layout.addWidget(self.current_path)
        import_button=QPushButton("Previsualizar o reemplazar desde otra base"); import_button.setObjectName("primaryButton"); import_button.setMinimumHeight(56)
        backup_button=QPushButton("Crear respaldo ahora"); backup_button.setMinimumHeight(50)
        export_button=QPushButton("Exportar base a Excel editable"); export_button.setMinimumHeight(50)
        reset_button=QPushButton("Restablecer Atlas a una base vacía"); reset_button.setMinimumHeight(50)
        location_button=QPushButton("Mostrar ubicación de la base de datos"); location_button.setMinimumHeight(50)
        layout.addSpacing(12)
        for w in (import_button,export_button,backup_button,reset_button,location_button): layout.addWidget(w)
        note=QLabel("La previsualización no escribe nada. La exportación Excel genera una fila editable por equipo y oculta los campos técnicos de la base. Reemplazar crea un respaldo, filtra duplicados de serie y verifica los conteos antes de activar la base."); note.setWordWrap(True); note.setObjectName("pageSubtitle"); layout.addSpacing(8); layout.addWidget(note); layout.addStretch(1)
        import_button.clicked.connect(self.import_database); export_button.clicked.connect(self.export_editable_excel); backup_button.clicked.connect(self.create_backup); reset_button.clicked.connect(self.reset_database); location_button.clicked.connect(self.show_database_path)

    def import_database(self):
        selected,_=QFileDialog.getOpenFileName(self,"Seleccionar base de datos existente","","Bases SQLite (*.db *.sqlite *.sqlite3);;Todos los archivos (*)")
        if not selected: return
        try: info=self.database.inspect_database(Path(selected))
        except Exception as e: QMessageBox.critical(self,"Base no válida",str(e)); return
        if info["mode"]=="unsupported":
            QMessageBox.warning(self,"Estructura no reconocida",f"No se encontraron tablas compatibles.\n\nTablas detectadas: {', '.join(info['tables']) or 'ninguna'}"); return
        skip_dupes=QMessageBox.question(self,"Filtro de series duplicadas","¿Omitir automáticamente los registros repetidos del mismo número de serie?\n\nSe conservará el primer registro de cada serie normalizada.",QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.Yes)==QMessageBox.StandardButton.Yes
        skip_blank=QMessageBox.question(self,"Equipos sin serie","¿Omitir también los equipos cuyo número de serie esté vacío?",QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)==QMessageBox.StandardButton.Yes
        try: preview=self.database.import_preview(Path(selected),skip_duplicate_serials=skip_dupes,skip_blank_serials=skip_blank)
        except Exception as e: QMessageBox.critical(self,"No se pudo analizar",str(e)); return
        current=self.database.inspect_database(database_path())
        current_eq=current["counts"].get("atlas_equipment",current["counts"].get("equipment",0))
        text=(f"BASE ACTIVA\nEquipos actuales: {current_eq}\n\nBASE SELECCIONADA\nEquipos encontrados: {preview['equipment_source']}\n"
              f"Registros duplicados de serie: {preview['duplicate_records']} en {preview['duplicate_groups']} grupos\n"
              f"Equipos sin serie: {preview['blank_serials']}\nEquipos después de filtros: {preview['equipment_after_filter']}\n\n"
              "Previsualizar no ha modificado ningún archivo.\n\n¿Reemplazar completamente la base activa con este resultado filtrado?")
        if QMessageBox.question(self,"Previsualización de importación",text,QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes: return
        try:
            result=self.database.replace_with_filtered_database(Path(selected),backups_dir(),skip_duplicate_serials=skip_dupes,skip_blank_serials=skip_blank)
            if self.refresh_callback: self.refresh_callback()
        except Exception as e: QMessageBox.critical(self,"La importación no se completó",f"{e}\n\nLa base anterior fue restaurada automáticamente."); return
        QMessageBox.information(self,"Reemplazo terminado",f"Dependencias: {result['dependencies']}\nEquipos finales: {result['equipment']}\nContadores: {result.get('counters',0)}\nRegistros filtrados: {result['skipped']}\n\nRespaldo anterior:\n{result['backup']}")


    def export_editable_excel(self):
        selected,_=QFileDialog.getSaveFileName(
            self,
            "Exportar base a Excel editable",
            "Atlas_inventario_editable.xlsx",
            "Libro de Excel (*.xlsx)",
        )
        if not selected: return
        path=Path(selected)
        if path.suffix.lower() != ".xlsx": path=path.with_suffix(".xlsx")
        try:
            rows=self.database.editable_excel_rows()
            count=export_editable_excel(path, rows)
        except Exception as e:
            QMessageBox.critical(self,"No se pudo exportar",str(e)); return
        QMessageBox.information(
            self,
            "Excel editable creado",
            f"Se exportaron {count} equipos.\n\nArchivo:\n{path}\n\n"
            "El archivo usa encabezados de negocio compatibles con el asistente de migración y no contiene IDs ni campos técnicos de Atlas.",
        )

    def reset_database(self):
        warning=("Esto eliminará de la base activa todos los edificios, dependencias, oficinas, personas, equipos, contadores y órdenes de servicio.\n\n"
                 "Atlas creará un respaldo automático antes de vaciarla.\n\n¿Continuar?")
        if QMessageBox.warning(self,"Restablecer a base vacía",warning,QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.Cancel,QMessageBox.StandardButton.Cancel)!=QMessageBox.StandardButton.Yes: return
        if QMessageBox.question(self,"Confirmación final","¿Está seguro? La base activa quedará vacía.",QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes: return
        try:
            backup=self.database.reset_to_empty(backups_dir())
            if self.refresh_callback: self.refresh_callback()
        except Exception as e: QMessageBox.critical(self,"No se pudo restablecer",str(e)); return
        QMessageBox.information(self,"Base vacía creada",f"Atlas quedó con una base operativa vacía.\n\nRespaldo anterior:\n{backup}")

    def create_backup(self):
        try: path=self.database.backup(backups_dir())
        except Exception as e: QMessageBox.critical(self,"No se pudo respaldar",str(e)); return
        QMessageBox.information(self,"Respaldo creado",f"Respaldo guardado en:\n\n{path}")

    def show_database_path(self):
        QMessageBox.information(self,"Base de datos portátil",f"La base activa se guarda en:\n\n{database_path()}")
