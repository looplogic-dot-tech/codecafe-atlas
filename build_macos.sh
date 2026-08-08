#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [[ ! -x ".venv/bin/python" ]]; then
  python3 -m venv .venv
fi

.venv/bin/python -m pip install --disable-pip-version-check -r requirements.txt

.venv/bin/python -m PyInstaller \
  --noconfirm \
  --clean \
  --windowed \
  --onedir \
  --name "CodeCafe-Atlas" \
  --add-data "modules:modules" \
  --add-data "assets:assets" \
  --icon "assets/codecafe_atlas_icon.png" \
  main.py

echo "Compilación terminada en dist/"
