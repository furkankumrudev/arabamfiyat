#!/usr/bin/env bash
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
require_python
exec "$PYTHON" -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000 --reload
