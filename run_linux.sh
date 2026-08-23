#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python3 bootstrap_dependencies.py
exec .venv/bin/python main.py
