from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import traceback
import zipfile
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QLabel, QMessageBox, QProgressBar, QVBoxLayout, QWidget

PRODUCT_NAME = "CodeCafe Atlas"
PRODUCT_SLUG = "CodeCafe-Atlas"
UPDATER_SLUG = "CodeCafe-Atlas-Updater"

MANIFEST_NAME = "update_manifest.json"
PAYLOAD_DIRECTORY = "payload"
PRESERVE = ("data", "backups")


def bundled_root() -> Path:
    bundle = getattr(sys, "_MEIPASS", None)
    return Path(bundle).resolve() if bundle else Path(__file__).resolve().parent


def asset_path(name: str) -> Path:
    return bundled_root() / "assets" / name


def wait_for_process(pid: int, timeout: int = 120) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if sys.platform.startswith("win"):
                result = subprocess.run(
                    ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                    capture_output=True, text=True,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                if str(pid) not in result.stdout:
                    return
            else:
                os.kill(pid, 0)
        except (OSError, ProcessLookupError):
            return
        time.sleep(0.35)
    raise RuntimeError(f"{PRODUCT_NAME} no se cerró dentro del tiempo esperado.")


def safe_extract(archive: zipfile.ZipFile, destination: Path) -> None:
    destination = destination.resolve()
    for member in archive.infolist():
        relative = Path(member.filename.replace("\\", "/"))
        if relative.is_absolute() or ".." in relative.parts:
            raise RuntimeError(f"Ruta insegura: {member.filename}")
        resolved = (destination / relative).resolve()
        if resolved != destination and destination not in resolved.parents:
            raise RuntimeError(f"Ruta insegura: {member.filename}")
    archive.extractall(destination)


def merge_directory(source: Path, destination: Path) -> None:
    if not source.exists():
        return
    destination.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        output = destination / item.name
        if item.is_dir():
            merge_directory(item, output)
        else:
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, output)


def apply_manifest_modes(root: Path, manifest: dict) -> None:
    if sys.platform.startswith("win"):
        return
    for entry in manifest.get("files", []):
        path = root / Path(str(entry.get("path") or ""))
        if not path.is_file():
            continue
        mode = entry.get("mode")
        try:
            numeric_mode = int(mode, 8) if isinstance(mode, str) else int(mode)
        except (TypeError, ValueError):
            numeric_mode = 0o644
        if entry.get("executable"):
            numeric_mode |= 0o755
        path.chmod(numeric_mode & 0o777)

    for executable_name in (PRODUCT_SLUG, UPDATER_SLUG):
        executable = root / executable_name
        if executable.is_file():
            executable.chmod(executable.stat().st_mode | 0o755)


def _main_name() -> str:
    suffix = ".exe" if sys.platform.startswith("win") else ""
    return f"{PRODUCT_SLUG}{suffix}"

def validate_payload_root(payload: Path) -> Path:
    name = _main_name()
    expected = payload / name
    if not expected.is_file():
        raise RuntimeError(f"Falta el ejecutable raíz {name}.")
    nested = payload / PRODUCT_SLUG / name
    if nested.exists():
        raise RuntimeError(f"El paquete contiene un nivel {PRODUCT_SLUG} adicional.")
    return expected

def restart_application(target: Path) -> None:
    name = _main_name()
    executable = target / name
    if not executable.is_file():
        raise RuntimeError(f"No se encontró el ejecutable instalado: {name}")
    if not sys.platform.startswith("win"):
        executable.chmod(executable.stat().st_mode | 0o755)
    subprocess.Popen([str(executable)], cwd=str(target), close_fds=not sys.platform.startswith("win"))

def perform_update(package: Path, target: Path, pid: int, progress, restart: bool = True) -> Path:
    progress(4, "Esperando a que CodeCafe Atlas se cierre…")
    if pid > 0:
        wait_for_process(pid)
    progress(12, "Extrayendo y validando el paquete…")
    temp_root = Path(tempfile.mkdtemp(prefix="codecafe-atlas-update-"))
    try:
        with zipfile.ZipFile(package, "r") as archive:
            manifest = json.loads(archive.read(MANIFEST_NAME).decode("utf-8"))
            safe_extract(archive, temp_root)
        payload = temp_root / PAYLOAD_DIRECTORY
        if not payload.is_dir():
            raise RuntimeError("El paquete no contiene payload/.")
        validate_payload_root(payload)
        apply_manifest_modes(payload, manifest)

        progress(28, "Preparando la nueva instalación…")
        staging = target.parent / f"{target.name}.update-new"
        if staging.exists():
            shutil.rmtree(staging)
        shutil.copytree(payload, staging, copy_function=shutil.copy2)
        apply_manifest_modes(staging, manifest)
        validate_payload_root(staging)

        progress(43, "Conservando datos y respaldos…")
        for name in PRESERVE:
            source_dir = target / name
            destination_dir = staging / name
            if destination_dir.exists():
                shutil.rmtree(destination_dir)
            merge_directory(source_dir, destination_dir)

        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = target.parent / f"{target.name}.backup-{stamp}"
        if backup.exists():
            shutil.rmtree(backup)

        progress(60, "Creando respaldo de la versión anterior…")
        target.rename(backup)
        try:
            progress(76, "Instalando la nueva versión…")
            staging.rename(target)
            apply_manifest_modes(target, manifest)
            validate_payload_root(target)
        except Exception:
            if target.exists():
                shutil.rmtree(target)
            backup.rename(target)
            raise

        progress(92, "Verificando permisos y ejecutable…")
        validate_payload_root(target)
        if restart:
            progress(97, "Abriendo la nueva versión…")
            restart_application(target)
        progress(100, "Actualización terminada.")
        return backup
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


class UpdateThread(QThread):
    progress_changed = Signal(int, str)
    succeeded = Signal(str)
    failed = Signal(str)

    def __init__(self, package: Path, target: Path, pid: int):
        super().__init__()
        self.package, self.target, self.pid = package, target, pid

    def run(self):
        try:
            backup = perform_update(self.package, self.target, self.pid, self.progress_changed.emit)
            self.succeeded.emit(str(backup))
        except Exception:
            self.failed.emit(traceback.format_exc())


class UpdaterWindow(QWidget):
    def __init__(self, args):
        super().__init__()
        self.setWindowTitle(f"Actualizador de {PRODUCT_NAME}")
        self.setWindowIcon(QIcon(str(asset_path("codecafe_atlas_icon.png"))))
        self.resize(580, 190)
        self.setFixedHeight(190)
        layout = QVBoxLayout(self)
        title = QLabel(f"Actualizando {PRODUCT_NAME}")
        title.setStyleSheet("font-size:20px;font-weight:800;")
        self.status = QLabel("Preparando actualización…")
        self.status.setWordWrap(True)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        layout.addWidget(title); layout.addWidget(self.status); layout.addWidget(self.progress)
        self.thread = UpdateThread(Path(args.package).resolve(), Path(args.target).resolve(), int(args.pid))
        self.thread.progress_changed.connect(self.on_progress)
        self.thread.succeeded.connect(self.on_success)
        self.thread.failed.connect(self.on_failure)
        self.thread.start()

    def closeEvent(self, event):
        event.ignore() if self.thread.isRunning() else event.accept()

    def on_progress(self, value: int, text: str):
        self.progress.setValue(value); self.status.setText(text)

    def on_success(self, backup_path: str):
        QMessageBox.information(self, "Actualización terminada", f"{PRODUCT_NAME} se actualizó correctamente.\n\nRespaldo:\n" + backup_path)
        self.close()

    def on_failure(self, details: str):
        QMessageBox.critical(self, "La actualización no se completó", "La instalación anterior fue restaurada cuando fue necesario.\n\n" + details[-3500:])
        self.close()


def parse_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--pid", required=True, type=int)
    parser.add_argument("--current-version", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_arguments()
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(str(asset_path("codecafe_atlas_icon.png"))))
    window = UpdaterWindow(args); window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
