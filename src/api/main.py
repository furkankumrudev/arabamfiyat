"""FastAPI entry point for the ArabamFiyat.com web application."""

from __future__ import annotations

import logging
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, closing
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.ingestion.sources.demo import DEMO_SOURCE
from src.maintenance.pipeline import last_success_at

from .database import DatabaseUnavailable, ListingRepository
from .dependencies import REPOSITORY
from .routes import catalog, market, sale_reports, valuation
from .schemas import HealthResponse
from .settings import cors_origins, web_dist_dir

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def _warm_listing_cache() -> None:
    try:
        REPOSITORY.warm()
    except DatabaseUnavailable:
        pass  # Nothing to warm yet; the first request reports it.
    except Exception:
        logger.exception("Listing cache warm-up failed")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # Read the listing table in the background at startup, so the first visitor
    # does not wait for hundreds of thousands of rows to load.
    threading.Thread(target=_warm_listing_cache, name="listing-cache-warmup", daemon=True).start()
    yield


app = FastAPI(title="ArabamFiyat.com API", version="0.1.0", docs_url="/docs", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)
app.include_router(catalog.router)
app.include_router(market.router)
app.include_router(valuation.router)
app.include_router(sale_reports.router)


# A daily pipeline that has not succeeded within this many hours is reported as
# stale, so a silently stopped data flow becomes visible instead of showing an
# ageing database as healthy.
PIPELINE_STALE_AFTER_HOURS = 36.0


def pipeline_freshness(connection) -> dict[str, object]:
    """Describe how recently the maintenance pipeline last completed."""
    last_success = last_success_at(connection)
    if last_success is None:
        return {"last_pipeline_success_at": None, "pipeline_age_hours": None, "pipeline_stale": None}
    try:
        finished = datetime.fromisoformat(last_success)
    except ValueError:
        logger.warning("Hat kaydindaki zaman damgasi okunamadi: %r", last_success)
        return {"last_pipeline_success_at": last_success, "pipeline_age_hours": None, "pipeline_stale": None}
    if finished.tzinfo is None:
        finished = finished.replace(tzinfo=UTC)
    age_hours = (datetime.now(UTC) - finished).total_seconds() / 3600
    return {
        "last_pipeline_success_at": last_success,
        "pipeline_age_hours": round(age_hours, 2),
        "pipeline_stale": age_hours > PIPELINE_STALE_AFTER_HOURS,
    }


def data_sources(connection, table: str) -> list[str]:
    """List the sources behind the analysed listings so demo data is never passed off as real."""
    columns = {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}
    if "source" not in columns:
        return []
    rows = connection.execute(f"SELECT DISTINCT source FROM {table} WHERE source IS NOT NULL ORDER BY source")
    return [str(row[0]) for row in rows]


@app.get("/api/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    repository = ListingRepository()
    try:
        with closing(repository.connect()) as connection:
            table = repository.listing_table(connection)
            count = int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            freshness = pipeline_freshness(connection)
            sources = data_sources(connection, table)
        status = "degraded" if freshness["pipeline_stale"] else "ok"
        return HealthResponse(
            status=status, database_available=True, table=table, listing_count=count,
            data_sources=sources, demo_data=DEMO_SOURCE in sources, **freshness
        )
    except DatabaseUnavailable as exc:
        return HealthResponse(status="unavailable", database_available=False, message=str(exc))
    except Exception:
        logger.exception("Health check failed")
        return HealthResponse(status="unavailable", database_available=False, message="Veritabanı okunamadı.")


def mount_web_app(application: FastAPI, dist: Path) -> None:
    """Serve the built React app from the API process for single-container hosting.

    Registered last so every API route wins; unknown paths fall back to
    index.html because the app routes on the client.
    """
    root = dist.resolve()
    if (root / "assets").is_dir():
        application.mount("/assets", StaticFiles(directory=root / "assets"), name="assets")

    @application.get("/{path:path}", include_in_schema=False)
    def web_app(path: str) -> FileResponse:
        if path.startswith("api/"):
            raise HTTPException(status_code=404)
        candidate = (root / path).resolve()
        if path and candidate.is_file() and root in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(root / "index.html")


if (dist := web_dist_dir()) is not None:
    mount_web_app(app, dist)
