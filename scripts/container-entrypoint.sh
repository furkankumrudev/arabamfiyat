#!/bin/sh
set -eu

# SQLite relies on file locking that is not reliable on a Windows bind mount, so
# the read-only seed database is copied onto the container filesystem. The target
# lives on a named volume: seed it once, then leave the accumulated snapshots and
# daily updates alone on every later start. Set RESEED_DB=1 to force a refresh.
if [ -n "${SOURCE_DB_PATH:-}" ] && [ -f "$SOURCE_DB_PATH" ]; then
    if [ ! -f "$SQLITE_DB_PATH" ] || [ "${RESEED_DB:-0}" = "1" ]; then
        mkdir -p "$(dirname "$SQLITE_DB_PATH")"
        cp "$SOURCE_DB_PATH" "$SQLITE_DB_PATH"
        echo "Seeded $SQLITE_DB_PATH from $SOURCE_DB_PATH"
    else
        echo "Using existing $SQLITE_DB_PATH (set RESEED_DB=1 to reseed)"
    fi
fi

# With no seed database at all, start from the synthetic demo set so a fresh
# `docker compose up` shows a working product. The UI labels it as demo data.
# Only the service that sets DEMO_DATA=1 (the API) does this.
if [ ! -f "$SQLITE_DB_PATH" ] && [ "${DEMO_DATA:-0}" = "1" ]; then
    echo "No database found; loading demo data into $SQLITE_DB_PATH"
    python -m src.ingestion.load_listings demo --db-path "$SQLITE_DB_PATH"
fi

exec "$@"
