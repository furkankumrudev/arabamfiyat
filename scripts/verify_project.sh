#!/usr/bin/env bash
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
require_python
require_web_deps

echo "[1/3] Ruff lint calisiyor..."
"$PYTHON" -m ruff check .

echo "[2/3] Python testleri calisiyor..."
"$PYTHON" -m unittest discover -s tests -v

echo "[3/3] React production build calisiyor..."
cd web
npm run build
