from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def _external_process_environment() -> dict[str, str]:
    """Return an environment safe for launching desktop applications.

    PyInstaller alters library-search variables for the frozen application.  If
    those values leak into Dolphin, gio or xdg-open, the external application can
    load Atlas' bundled Qt/system libraries and fail before showing a window.
    Restore the pre-PyInstaller values for child desktop processes.
    """
    env = os.environ.copy()
    if sys.platform.startswith("linux"):
        original = env.get("LD_LIBRARY_PATH_ORIG")
        if original is not None:
            if original:
                env["LD_LIBRARY_PATH"] = original
            else:
                env.pop("LD_LIBRARY_PATH", None)
        else:
            env.pop("LD_LIBRARY_PATH", None)

        # PyInstaller may add its extraction directory to loader variables.
        # These must not be inherited by unrelated desktop applications.
        for name in ("LIBPATH", "SHLIB_PATH"):
            original_name = f"{name}_ORIG"
            if original_name in env:
                original_value = env.get(original_name, "")
                if original_value:
                    env[name] = original_value
                else:
                    env.pop(name, None)
    return env


def _folder_commands(folder: Path) -> list[list[str]]:
    commands: list[list[str]] = []
    if sys.platform.startswith("linux"):
        candidates = (
            ("dolphin", ["--new-window", str(folder)]),
            ("kioclient6", ["exec", str(folder)]),
            ("kioclient5", ["exec", str(folder)]),
            ("gio", ["open", str(folder)]),
            ("xdg-open", [str(folder)]),
        )
        for executable_name, args in candidates:
            executable = shutil.which(executable_name)
            if executable:
                commands.append([executable, *args])
    elif sys.platform == "darwin":
        commands.append([shutil.which("open") or "open", str(folder)])
    elif sys.platform.startswith("win"):
        commands.append([
            shutil.which("explorer.exe") or shutil.which("explorer") or "explorer.exe",
            str(folder),
        ])
    return commands



def _file_commands(file_path: Path) -> list[list[str]]:
    """Return native commands for opening a file with the desktop default app."""
    commands: list[list[str]] = []
    if sys.platform.startswith("linux"):
        candidates = (
            ("kioclient6", ["exec", str(file_path)]),
            ("kioclient5", ["exec", str(file_path)]),
            ("gio", ["open", str(file_path)]),
            ("xdg-open", [str(file_path)]),
        )
        for executable_name, args in candidates:
            executable = shutil.which(executable_name)
            if executable:
                commands.append([executable, *args])
        # Last-resort direct office launch for generated .xlsx files.  This is
        # intentionally after the desktop-default launchers so the user's file
        # association remains authoritative whenever it works.
        if file_path.suffix.casefold() in {".xlsx", ".xls", ".ods"}:
            for office_name in ("libreoffice", "soffice"):
                executable = shutil.which(office_name)
                if executable:
                    commands.append([executable, str(file_path)])
                    break
    elif sys.platform == "darwin":
        commands.append([shutil.which("open") or "open", str(file_path)])
    elif sys.platform.startswith("win"):
        # cmd /c start delegates to the registered Windows file association.
        commands.append(["cmd", "/c", "start", "", str(file_path)])
    return commands


def open_file_native(path: str | Path, *, probe_seconds: float = 1.2) -> tuple[bool, str]:
    """Open *path* using the operating system's registered desktop application.

    This mirrors :func:`open_directory_native` but is specifically for files.
    On frozen Linux builds it removes PyInstaller's bundled library paths before
    starting KDE/GNOME/LibreOffice.  QDesktopServices inherits those paths and
    can therefore work on Windows while failing silently on Linux.
    """
    file_path = Path(path).expanduser().resolve()
    if not file_path.exists() or not file_path.is_file():
        return False, f"El archivo no existe: {file_path}"

    commands = _file_commands(file_path)
    if not commands:
        return False, "No se encontró una aplicación compatible para abrir el archivo."

    env = _external_process_environment()
    failures: list[str] = []
    for command in commands:
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=not sys.platform.startswith("win"),
                env=env,
                text=True,
            )
            try:
                stdout, stderr = process.communicate(timeout=probe_seconds)
            except subprocess.TimeoutExpired:
                return True, " ".join(command)
            if process.returncode == 0:
                return True, " ".join(command)
            detail = (stderr or stdout or "").strip().replace("\n", " ")[:400]
            failures.append(f"{' '.join(command)} -> {process.returncode}: {detail}")
        except (OSError, subprocess.SubprocessError) as error:
            failures.append(f"{' '.join(command)} -> {error}")
    return False, "\n".join(failures)

def open_directory_native(path: str | Path, *, probe_seconds: float = 0.8) -> tuple[bool, str]:
    """Open *path* in the graphical file manager.

    Returns ``(success, diagnostic)``.  External applications are launched with
    PyInstaller's bundled library paths removed so KDE/GNOME helpers use their
    own system libraries.
    """
    folder = Path(path).expanduser().resolve()
    folder.mkdir(parents=True, exist_ok=True)
    commands = _folder_commands(folder)
    if not commands:
        return False, "No se encontró un administrador de archivos compatible en PATH."

    env = _external_process_environment()
    failures: list[str] = []
    for command in commands:
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=not sys.platform.startswith("win"),
                env=env,
                text=True,
            )
            try:
                stdout, stderr = process.communicate(timeout=probe_seconds)
            except subprocess.TimeoutExpired:
                # A graphical file manager that remains alive accepted the request.
                return True, " ".join(command)
            if process.returncode == 0:
                return True, " ".join(command)
            detail = (stderr or stdout or "").strip().replace("\n", " ")[:400]
            failures.append(f"{' '.join(command)} -> {process.returncode}: {detail}")
        except (OSError, subprocess.SubprocessError) as error:
            failures.append(f"{' '.join(command)} -> {error}")
    return False, "\n".join(failures)
