from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
REQUIREMENTS = ROOT / "requirements.txt"
CACHE_ROOT = ROOT / "packages"
STATE_FILE = CACHE_ROOT / "cache_state.json"


def platform_slug() -> str:
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"


def machine_slug() -> str:
    value = platform.machine().lower() or "unknown"
    return {"amd64": "x86_64", "x64": "x86_64", "x86_64": "x86_64", "aarch64": "arm64"}.get(value, value)


def python_tag() -> str:
    return f"py{sys.version_info.major}{sys.version_info.minor}"


def cache_dir() -> Path:
    return CACHE_ROOT / f"{platform_slug()}-{machine_slug()}" / python_tag()


def venv_python() -> Path:
    return VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def run(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    print("+", " ".join(str(part) for part in command))
    return subprocess.run(command, cwd=ROOT, text=True, check=check)


def pip_is_healthy(python: Path) -> bool:
    if not python.is_file():
        return False
    probe = subprocess.run(
        [
            str(python),
            "-c",
            (
                "import pip, pip._internal.utils, sys; "
                "print(f'{sys.version_info.major}.{sys.version_info.minor} pip={pip.__version__}')"
            ),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return probe.returncode == 0


def existing_venv_matches() -> bool:
    python = venv_python()
    if not python.is_file():
        return False
    probe = subprocess.run(
        [str(python), "-c", "import json,sys; print(json.dumps([sys.version_info.major,sys.version_info.minor]))"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if probe.returncode != 0:
        return False
    try:
        major, minor = json.loads(probe.stdout.strip())
    except Exception:
        return False
    if (major, minor) != (sys.version_info.major, sys.version_info.minor):
        return False
    return pip_is_healthy(python)


def ensure_venv() -> Path:
    if VENV.exists() and not existing_venv_matches():
        print(f"Virtual environment incompatible or damaged (including pip); recreating {VENV}")
        shutil.rmtree(VENV, ignore_errors=True)
    if not venv_python().is_file():
        print(f"Creating virtual environment with Python {sys.version.split()[0]}...")
        venv.EnvBuilder(with_pip=True, clear=False).create(VENV)

    python = venv_python()
    if not pip_is_healthy(python):
        print("pip inside the virtual environment is incomplete; repairing it with ensurepip...")
        repair = subprocess.run(
            [str(python), "-m", "ensurepip", "--upgrade"],
            cwd=ROOT,
            text=True,
        )
        if repair.returncode != 0 or not pip_is_healthy(python):
            print("Automatic pip repair failed; recreating the virtual environment once...")
            shutil.rmtree(VENV, ignore_errors=True)
            venv.EnvBuilder(with_pip=True, clear=False).create(VENV)
            python = venv_python()
            if not pip_is_healthy(python):
                raise SystemExit("ERROR: Python created a virtual environment with a broken pip installation.")
    return python


def offline_install(python: Path, cache: Path, requirement_file: Path) -> bool:
    result = run(
        [
            str(python), "-m", "pip", "install", "--disable-pip-version-check",
            "--no-index", "--find-links", str(cache), "-r", str(requirement_file),
        ],
        check=False,
    )
    return result.returncode == 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare CodeCafe Atlas build dependencies with a persistent offline cache.")
    parser.add_argument("--offline", action="store_true", help="Never access the Internet; fail if the local package cache is incomplete.")
    args = parser.parse_args()

    if not REQUIREMENTS.is_file():
        raise SystemExit("ERROR: requirements.txt is missing.")

    CACHE_ROOT.mkdir(exist_ok=True)
    cache = cache_dir()
    cache.mkdir(parents=True, exist_ok=True)
    python = ensure_venv()
    lock = cache / "resolved-requirements.txt"
    install_requirements = lock if lock.is_file() else REQUIREMENTS

    print(f"Dependency cache: {cache}")
    if offline_install(python, cache, install_requirements):
        print("Dependencies satisfied from the local Atlas package cache.")
    else:
        if args.offline:
            raise SystemExit("ERROR: local package cache is incomplete and --offline was requested.")
        print("Local cache is incomplete. Downloading only what pip needs into the persistent Atlas cache...")
        run([str(python), "-m", "pip", "download", "--disable-pip-version-check", "--dest", str(cache), "-r", str(REQUIREMENTS)])
        if not offline_install(python, cache, REQUIREMENTS):
            raise SystemExit("ERROR: packages were downloaded but offline installation still failed.")
        freeze = subprocess.run([str(python), "-m", "pip", "freeze"], cwd=ROOT, capture_output=True, text=True, check=True)
        lock.write_text(freeze.stdout, encoding="utf-8")
        print(f"Saved resolved dependency lock: {lock}")

    STATE_FILE.write_text(
        json.dumps(
            {
                "platform": platform_slug(),
                "architecture": machine_slug(),
                "python": sys.version.split()[0],
                "python_tag": python_tag(),
                "active_cache": str(cache.relative_to(ROOT)).replace("\\", "/"),
            },
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    print("Dependency bootstrap complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
