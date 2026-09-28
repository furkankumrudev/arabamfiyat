#!/usr/bin/env bash
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
require_python
exec "$PYTHON" -m src.ml.predict_price_model "$@"
