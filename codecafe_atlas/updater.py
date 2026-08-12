from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .paths import application_root
from .identity import (
    PRODUCT_NAME, PRODUCT_SLUG, UPDATER_SLUG,
)

MANIFEST_NAME = "update_manifest.json"
SUPPORTED_PRODUCT = PRODUCT_NAME
PAYLOAD_DIRECTORY = "payload"
MAIN_EXECUTABLES = {
    "windows": f"{PRODUCT_SLUG}.exe",
    "linux": PRODUCT_SLUG,
    "macos": PRODUCT_SLUG,
}


class UpdatePackageError(RuntimeError):
    pass


@dataclass(frozen=True)
class UpdatePackageInfo:
    package_path: Path
    version: str
    platform_name: str
    architecture: str
    release_notes: str
    file_count: int
    total_size: int
    manifest: dict[str, Any]


def version_tuple(version: str) -> tuple[int, ...]:
    parts = re.findall(r"\d+", str(version or ""))
    return tuple(int(part) for part in parts) if parts else (0,)


def current_platform_name() -> str:
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"


def current_architecture() -> str:
    machine = platform.machine().lower()
    return {
        "amd64": "x86_64",
        "x64": "x86_64",
        "x86-64": "x86_64",
        "aarch64": "arm64",
    }.get(machine, machine or "unknown")


def _safe_member_path(name: str) -> Path:
    path = Path(str(name).replace("\\", "/"))
    if not str(name).strip() or path.is_absolute() or ".." in path.parts:
        raise UpdatePackageError(f"Ruta no permitida en el paquete: {name}")
    return path


def read_update_manifest(package_path: str | Path) -> dict[str, Any]:
    package = Path(package_path).resolve()
    if not package.is_file():
        raise UpdatePackageError("El paquete de actualización no existe.")
    if package.suffix.lower() != ".zip":
        raise UpdatePackageError("La actualización debe ser un archivo ZIP.")

    try:
        with zipfile.ZipFile(package, "r") as archive:
            for name in archive.namelist():
                _safe_member_path(name)
            if MANIFEST_NAME not in archive.namelist():
                raise UpdatePackageError(f"Falta {MANIFEST_NAME}.")
            raw = archive.read(MANIFEST_NAME)
    except zipfile.BadZipFile as error:
        raise UpdatePackageError("El ZIP está dañado o no es válido.") from error

    try:
        manifest = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise UpdatePackageError("El manifiesto no es válido.") from error

    if manifest.get("product") != SUPPORTED_PRODUCT:
        raise UpdatePackageError(f"El paquete no corresponde a {PRODUCT_NAME}.")
    schema = int(manifest.get("schema", 0))
    if schema < 2:
        raise UpdatePackageError(
            "El paquete usa el formato antiguo del actualizador. "
            "Debe generarse nuevamente con v0.23.1 o posterior."
        )
    if schema >= 3 and manifest.get("application_id") != "io.codecafe.atlas":
        raise UpdatePackageError("El Application ID del paquete no corresponde a CodeCafe Atlas.")
    if schema >= 3 and manifest.get("origin_id") != "CCA-JSS-2026":
        raise UpdatePackageError("El Origin ID del paquete no corresponde a CodeCafe Atlas.")
    for key in ("version", "platform", "architecture", "files", "payload_directory"):
        if key not in manifest:
            raise UpdatePackageError(f"Falta el campo {key} en el manifiesto.")
    if manifest["payload_directory"] != PAYLOAD_DIRECTORY:
        raise UpdatePackageError("La estructura del paquete no es compatible.")
    if not isinstance(manifest["files"], list) or not manifest["files"]:
        raise UpdatePackageError("El paquete no contiene archivos declarados.")
    return manifest


def inspect_update_package(
    package_path: str | Path,
    current_version: str,
    require_newer: bool = True,
) -> UpdatePackageInfo:
    package = Path(package_path).resolve()
    manifest = read_update_manifest(package)
    package_platform = str(manifest["platform"]).lower()
    local_platform = current_platform_name()
    if package_platform not in (local_platform, "any"):
        raise UpdatePackageError(
            f"El paquete es para {package_platform}; esta PC usa {local_platform}."
        )
    package_arch = str(manifest["architecture"]).lower()
    local_arch = current_architecture()
    if package_arch not in (local_arch, "any", "universal"):
        raise UpdatePackageError(
            f"El paquete es para {package_arch}; esta PC usa {local_arch}."
        )
    version = str(manifest["version"]).strip()
    if require_newer and version_tuple(version) <= version_tuple(current_version):
        raise UpdatePackageError(
            f"La versión {version} no es más reciente que {current_version}."
        )

    expected_main = MAIN_EXECUTABLES.get(package_platform, MAIN_EXECUTABLES[local_platform])
    declared_paths: set[str] = set()
    total_size = 0
    with zipfile.ZipFile(package, "r") as archive:
        names = set(archive.namelist())
        for entry in manifest["files"]:
            relative = _safe_member_path(entry.get("path", ""))
            relative_name = relative.as_posix()
            if relative_name in declared_paths:
                raise UpdatePackageError(f"Archivo duplicado: {relative_name}")
            declared_paths.add(relative_name)
            member = (Path(PAYLOAD_DIRECTORY) / relative).as_posix()
            if member not in names:
                raise UpdatePackageError(f"Falta el archivo {relative_name}.")
            expected_hash = str(entry.get("sha256") or "").lower()
            if len(expected_hash) != 64:
                raise UpdatePackageError(f"Hash inválido para {relative_name}.")
            data = archive.read(member)
            if hashlib.sha256(data).hexdigest() != expected_hash:
                raise UpdatePackageError(f"El archivo {relative_name} está dañado.")
            total_size += len(data)

    if expected_main not in declared_paths:
        raise UpdatePackageError(
            f"El paquete no contiene el ejecutable raíz {expected_main}."
        )
    nested_main = f"{PRODUCT_SLUG}/{expected_main}"
    if nested_main in declared_paths:
        raise UpdatePackageError(
            f"El paquete contiene una carpeta {PRODUCT_SLUG} anidada incorrectamente."
        )

    return UpdatePackageInfo(
        package_path=package,
        version=version,
        platform_name=package_platform,
        architecture=package_arch,
        release_notes=str(manifest.get("release_notes") or "").strip(),
        file_count=len(manifest["files"]),
        total_size=total_size,
        manifest=manifest,
    )


def updater_program_path() -> Path:
    root = application_root()
    return root / (f"{UPDATER_SLUG}.exe" if sys.platform.startswith("win") else UPDATER_SLUG)

def launch_external_updater(package_path: str | Path, current_version: str) -> None:
    package = Path(package_path).resolve()
    target = application_root().resolve()
    updater = updater_program_path()
    if getattr(sys, "frozen", False):
        if not updater.is_file():
            raise UpdatePackageError(
                f"No se encontró {UPDATER_SLUG} junto a la aplicación."
            )
        suffix = updater.suffix or ""
        temp_updater = Path(tempfile.gettempdir()) / f"{UPDATER_SLUG}-{uuid.uuid4().hex}{suffix}"
        shutil.copy2(updater, temp_updater)
        if not sys.platform.startswith("win"):
            temp_updater.chmod(temp_updater.stat().st_mode | 0o755)
        command = [str(temp_updater)]
    else:
        source_updater = target / "codecafe_atlas_updater.py"
        if not source_updater.is_file():
            raise UpdatePackageError("No se encontró codecafe_atlas_updater.py.")
        command = [sys.executable, str(source_updater)]

    command.extend([
        "--package", str(package),
        "--target", str(target),
        "--pid", str(os.getpid()),
        "--current-version", current_version,
    ])
    creation_flags = 0
    if sys.platform.startswith("win"):
        creation_flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen(
        command,
        cwd=str(target.parent),
        close_fds=not sys.platform.startswith("win"),
        creationflags=creation_flags,
    )
