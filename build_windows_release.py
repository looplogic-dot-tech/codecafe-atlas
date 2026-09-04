from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VERSION = "1.0.24.43"
PRODUCT = "CodeCafe-Atlas"
UPDATER = "CodeCafe-Atlas-Updater"


def run(command: list[str], cwd: Path = ROOT) -> None:
    print("+", " ".join(str(part) for part in command))
    subprocess.run(command, cwd=cwd, check=True)


def safe_rmtree(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)


def smoke_test(executable: Path) -> None:
    print(f"Smoke-testing Windows executable from local path: {executable}")
    proc = subprocess.Popen([str(executable)], cwd=executable.parent)
    time.sleep(3.0)
    code = proc.poll()
    if code is not None:
        raise RuntimeError(f"Windows executable exited during startup smoke test with code {code}.")
    proc.terminate()
    try:
        proc.wait(timeout=8)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)
    print("Windows local-path startup smoke test passed.")


def zip_tree(source: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(source.rglob("*")):
            if path.is_file():
                archive.write(path, Path(PRODUCT) / path.relative_to(source))


def main() -> int:
    if not sys.platform.startswith("win"):
        raise SystemExit("ERROR: build_windows_release.py must run on Windows.")

    local_base = Path(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()) / "CodeCafeAtlasBuild" / VERSION
    local_build = local_base / "build"
    local_dist = local_base / "dist"
    local_spec = local_base / "spec"
    safe_rmtree(local_base)
    local_build.mkdir(parents=True, exist_ok=True)
    local_dist.mkdir(parents=True, exist_ok=True)
    local_spec.mkdir(parents=True, exist_ok=True)

    python = Path(sys.executable)
    common = [str(python), "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed"]
    run(common + [
        "--onedir", "--name", PRODUCT,
        "--workpath", str(local_build / PRODUCT),
        "--distpath", str(local_dist),
        "--specpath", str(local_spec),
        "--add-data", f"{ROOT / 'modules'};modules",
        "--add-data", f"{ROOT / 'assets'};assets",
        "--icon", str(ROOT / "assets" / "codecafe_atlas_icon.ico"),
        str(ROOT / "main.py"),
    ])
    run(common + [
        "--onefile", "--name", UPDATER,
        "--workpath", str(local_build / UPDATER),
        "--distpath", str(local_dist),
        "--specpath", str(local_spec),
        "--add-data", f"{ROOT / 'assets'};assets",
        "--icon", str(ROOT / "assets" / "codecafe_atlas_icon.ico"),
        str(ROOT / "codecafe_atlas_updater.py"),
    ])

    final = local_dist / PRODUCT
    shutil.copy2(local_dist / f"{UPDATER}.exe", final / f"{UPDATER}.exe")
    (final / "data").mkdir(exist_ok=True)
    (final / "backups").mkdir(exist_ok=True)
    shutil.copy2(ROOT / "CODECAFE_ATLAS_IDENTITY.json", final / "CODECAFE_ATLAS_IDENTITY.json")

    main_exe = final / f"{PRODUCT}.exe"
    updater_exe = final / f"{UPDATER}.exe"
    if not main_exe.is_file() or not updater_exe.is_file():
        raise RuntimeError("Final Windows distribution is incomplete.")

    # Critical v1.0.24.25 gate: test before copying into a synced/source path.
    smoke_test(main_exe)

    source_dist = ROOT / "dist"
    safe_rmtree(source_dist)
    source_dist.mkdir(parents=True)
    shutil.copytree(final, source_dist / PRODUCT)

    release_zip = ROOT / "release" / f"CodeCafe_Atlas_v{VERSION}_Windows_x64.zip"
    zip_tree(final, release_zip)
    print(f"Windows distribution copied to: {source_dist / PRODUCT}")
    print(f"Portable ZIP created: {release_zip}")
    print("IMPORTANT: extract the portable ZIP before running Atlas. A local, non-synchronized folder is recommended.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
