from __future__ import annotations

import argparse
import hashlib
import json
import platform
import stat
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def default_platform() -> str:
    if sys.platform.startswith("win"): return "windows"
    if sys.platform == "darwin": return "macos"
    return "linux"


def default_architecture() -> str:
    machine = platform.machine().lower()
    return {"amd64":"x86_64", "x64":"x86_64", "aarch64":"arm64"}.get(machine, machine or "unknown")


def validate_distribution(dist: Path, platform_name: str) -> str:
    base = "CodeCafe-Atlas"
    expected = f"{base}.exe" if platform_name == "windows" else base
    main = dist / expected
    if main.is_dir():
        raise SystemExit(f"ERROR: {main} es una carpeta. Debe ser el archivo ejecutable raíz.")
    if not main.is_file():
        raise SystemExit(f"ERROR: falta el ejecutable raíz {expected} en {dist}")
    nested = dist / "CodeCafe-Atlas" / expected
    if nested.exists():
        raise SystemExit(f"ERROR: la distribución tiene un nivel de producto anidado ({nested.parent.name}).")
    updater_base = "CodeCafe-Atlas-Updater"
    updater = dist / (f"{updater_base}.exe" if platform_name == "windows" else updater_base)
    if not updater.is_file():
        raise SystemExit(f"ERROR: falta {updater.name} dentro de la carpeta final.")
    return expected


def main() -> int:
    parser = argparse.ArgumentParser(description="Crear paquete de actualización de CodeCafe Atlas.")
    parser.add_argument("--dist", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--platform", default=default_platform())
    parser.add_argument("--architecture", default=default_architecture())
    parser.add_argument("--notes", default="")
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    dist = Path(args.dist).resolve()
    if not dist.is_dir():
        raise SystemExit(f"No existe la carpeta de distribución: {dist}")
    validate_distribution(dist, args.platform)
    package_slug = "CodeCafe-Atlas"
    output = Path(args.output).resolve() if args.output else dist.parent / f"{package_slug}-update-{args.version}-{args.platform}-{args.architecture}.zip"
    notes = args.notes
    if notes and Path(notes).is_file():
        notes = Path(notes).read_text(encoding="utf-8")

    files = []
    for path in sorted(dist.rglob("*")):
        if not path.is_file(): continue
        relative = path.relative_to(dist)
        if relative.parts and relative.parts[0] in {"data", "backups"}: continue
        mode = stat.S_IMODE(path.stat().st_mode)
        files.append({
            "path": relative.as_posix(),
            "sha256": sha256_file(path),
            "size": path.stat().st_size,
            "mode": format(mode, "04o"),
            "executable": bool(mode & 0o111),
        })
    if not files: raise SystemExit("La distribución no contiene archivos.")
    manifest = {
        "schema": 3,
        "product": "CodeCafe Atlas",
        "application_id": "io.codecafe.atlas",
        "origin_id": "CCA-JSS-2026",
        "author": "Jaime Sánchez Sáenz",
        "version": args.version,
        "platform": args.platform,
        "architecture": args.architecture,
        "payload_directory": "payload",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "release_notes": notes,
        "preserve": ["data", "backups"],
        "files": files,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=7) as archive:
        archive.writestr("update_manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        for entry in files:
            source = dist / entry["path"]
            info = zipfile.ZipInfo((Path("payload") / entry["path"]).as_posix())
            info.date_time = tuple(datetime.fromtimestamp(source.stat().st_mtime).timetuple()[:6])
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (int(entry["mode"], 8) & 0xFFFF) << 16
            with source.open("rb") as handle:
                archive.writestr(info, handle.read())
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
