#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

python3 bootstrap_dependencies.py
.venv/bin/python validate_public_identity.py
.venv/bin/python validate_full_functionality.py
.venv/bin/python validate_before_build.py
rm -rf build dist

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
