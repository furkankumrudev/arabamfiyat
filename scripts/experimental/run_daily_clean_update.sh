#!/usr/bin/env bash
# The clean-claimed variant of the daily pull.
SCRIPT_DIR="$(dirname "${BASH_SOURCE[0]}")"
SEGMENT=clean \
CHECKPOINT=data/runtime/daily_clean_recent_checkpoint.json \
exec "$SCRIPT_DIR/run_daily_update.sh" "$@"
