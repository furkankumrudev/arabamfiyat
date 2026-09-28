"""Runtime settings shared by the local API and deployment configuration."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


def _path_from_environment(name: str, default: Path) -> Path:
    value = os.getenv(name)
    if not value:
        return default
    candidate = Path(value).expanduser()
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


@lru_cache(maxsize=1)
def sqlite_db_path() -> Path:
    """Return the local or mounted SQLite database configured for this runtime."""
    return _path_from_environment(
        "SQLITE_DB_PATH",
        PROJECT_ROOT / "data" / "runtime" / "vehicle_listings.sqlite3",
    )


@lru_cache(maxsize=1)
def cors_origins() -> list[str]:
    """Accept local Vite by default and allow explicit production origins."""
    configured = os.getenv("CORS_ORIGINS", "")
    origins = [origin.strip() for origin in configured.split(",") if origin.strip()]
    return origins or [
        "http://127.0.0.1:5173", "http://localhost:5173",
        "http://127.0.0.1:5174", "http://localhost:5174",
    ]


def web_dist_dir() -> Path | None:
    """The built web app to serve from the API, when WEB_DIST_DIR points at one."""
    value = os.getenv("WEB_DIST_DIR")
    if not value:
        return None
    path = _path_from_environment("WEB_DIST_DIR", PROJECT_ROOT / "web" / "dist")
    return path if (path / "index.html").is_file() else None
