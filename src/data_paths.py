"""Shared paths for local, non-versioned runtime data."""

from __future__ import annotations

from src.api.settings import PROJECT_ROOT, sqlite_db_path

# One database for every command: SQLITE_DB_PATH from .env when set, otherwise
# data/runtime/vehicle_listings.sqlite3. The API reads the same setting.
DEFAULT_DB_PATH = sqlite_db_path()

__all__ = ["DEFAULT_DB_PATH", "PROJECT_ROOT"]
