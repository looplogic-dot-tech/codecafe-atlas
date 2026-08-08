#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

python3 validate_before_build.py
python3 validate_public_identity.py

if [[ ! -x ".venv/bin/python" ]]; then
  python3 -m venv .venv
fi

.venv/bin/python -m pip install --disable-pip-version-check -r requirements.txt

rm -rf build dist

.venv/bin/python -m PyInstaller --noconfirm --clean --windowed --onedir --name "CodeCafe-Atlas" --add-data "modules:modules" --add-data "assets:assets" --icon "assets/codecafe_atlas_icon.png" main.py
.venv/bin/python -m PyInstaller --noconfirm --clean --windowed --onefile --name "CodeCafe-Atlas-Updater" --add-data "assets:assets" --icon "assets/codecafe_atlas_icon.png" codecafe_atlas_updater.py

cp -f dist/CodeCafe-Atlas-Updater dist/CodeCafe-Atlas/CodeCafe-Atlas-Updater
mkdir -p dist/CodeCafe-Atlas/data dist/CodeCafe-Atlas/backups
cp -f CODECAFE_ATLAS_IDENTITY.json dist/CodeCafe-Atlas/CODECAFE_ATLAS_IDENTITY.json
chmod +x dist/CodeCafe-Atlas/CodeCafe-Atlas dist/CodeCafe-Atlas/CodeCafe-Atlas-Updater
rm -f dist/CodeCafe-Atlas-Updater

echo "Probando arranque del ejecutable..."
LOG="$(mktemp)"
set +e
QT_QPA_PLATFORM=offscreen timeout 12s dist/CodeCafe-Atlas/CodeCafe-Atlas >"$LOG" 2>&1
STATUS=$?
set -e
if grep -qE "Traceback|AttributeError|Failed to execute script" "$LOG"; then
  cat "$LOG" >&2; rm -f "$LOG"; echo "ERROR: el ejecutable compilado no arranca." >&2; exit 1
fi
if [[ $STATUS -ne 0 && $STATUS -ne 124 ]]; then
  cat "$LOG" >&2; rm -f "$LOG"; echo "ERROR: prueba de arranque terminó con código $STATUS." >&2; exit 1
fi
rm -f "$LOG"
echo "Compilación y prueba de arranque correctas."
echo ".venv/bin/python make_update_package.py --dist dist/CodeCafe-Atlas --version 1.0.24.15 --platform linux --architecture x86_64"
