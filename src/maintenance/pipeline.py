"""Run the unattended maintenance steps and record what actually happened.

Ingestion is deliberately not part of this pipeline. The listing scraper drives
a real browser and can require a manual access check, so it stays an operator
command. Everything downstream of the raw table runs without supervision.
"""

from __future__ import annotations

import argparse
import logging
import sqlite3
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from src.api.database import ListingRepository
from src.api.settings import PROJECT_ROOT, sqlite_db_path
from src.ingestion.tsb_reference import import_new_files
from src.maintenance.clean_vehicle_data import CATALOG_PATH, CleanRules, clean_database
from src.maintenance.save_market_snapshot import save_snapshot

logger = logging.getLogger(__name__)

RUN_TABLE = "pipeline_runs"
STEP_CLEAN = "clean_vehicle_data"
STEP_SNAPSHOT = "save_market_snapshot"
STEP_REFERENCE = "import_reference_values"

STATUS_SUCCESS = "success"
STATUS_FAILED = "failed"
STATUS_SKIPPED = "skipped"

# Monthly reference lists are dropped here; the daily run picks up new periods.
REFERENCE_INBOX = PROJECT_ROOT / "data" / "reference" / "kasko"


class NothingToDo(Exception):
    """Raised by a step that had no work this run. Not a failure."""


@dataclass(frozen=True, slots=True)
class StepResult:
    """Outcome of one pipeline step."""

    step: str
    status: str
    started_at: str
    finished_at: str
    detail: str

    @property
    def succeeded(self) -> bool:
        # Nothing to do is not a failure: the reference list is published
        # monthly while this pipeline runs every day.
        return self.status in {STATUS_SUCCESS, STATUS_SKIPPED}


def utc_now() -> datetime:
    return datetime.now(UTC)


def ensure_run_table(connection: sqlite3.Connection) -> None:
    """Create the run log. It is append-only and never backfilled."""
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {RUN_TABLE} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            step TEXT NOT NULL,
            status TEXT NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT NOT NULL,
            detail TEXT
        )
        """
    )
    connection.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{RUN_TABLE}_step_finished ON {RUN_TABLE}(step, status, finished_at)"
    )
    connection.commit()


def record_step(connection: sqlite3.Connection, result: StepResult) -> None:
    ensure_run_table(connection)
    connection.execute(
        f"INSERT INTO {RUN_TABLE} (step, status, started_at, finished_at, detail) VALUES (?, ?, ?, ?, ?)",
        (result.step, result.status, result.started_at, result.finished_at, result.detail),
    )
    connection.commit()


def last_success_at(connection: sqlite3.Connection, step: str | None = None) -> str | None:
    """Return the newest successful finish time, optionally for one step."""
    if not _table_exists(connection, RUN_TABLE):
        return None
    if step:
        row = connection.execute(
            f"SELECT MAX(finished_at) FROM {RUN_TABLE} WHERE step = ? AND status = ?",
            (step, STATUS_SUCCESS),
        ).fetchone()
    else:
        # The pipeline is only as fresh as its slowest successful step.
        row = connection.execute(
            f"""SELECT MIN(latest) FROM (
                    SELECT MAX(finished_at) AS latest FROM {RUN_TABLE}
                    WHERE status = ? AND step IN (?, ?) GROUP BY step
                )""",
            (STATUS_SUCCESS, STEP_CLEAN, STEP_SNAPSHOT),
        ).fetchone()
        if row and row[0] is not None:
            completed_steps = connection.execute(
                f"SELECT COUNT(DISTINCT step) FROM {RUN_TABLE} WHERE status = ? AND step IN (?, ?)",
                (STATUS_SUCCESS, STEP_CLEAN, STEP_SNAPSHOT),
            ).fetchone()[0]
            if int(completed_steps) < 2:
                return None
    return str(row[0]) if row and row[0] is not None else None


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
    ).fetchone()
    return row is not None


def run_step(connection: sqlite3.Connection, step: str, action: Callable[[], str]) -> StepResult:
    """Run one step, record its outcome, and never raise past this boundary."""
    started = utc_now()
    try:
        detail = action()
        status = STATUS_SUCCESS
    except NothingToDo as nothing:
        detail = str(nothing)
        status = STATUS_SKIPPED
    except Exception as error:  # noqa: BLE001 - a failed step must not stop the pipeline
        logger.exception("Pipeline step failed: %s", step)
        detail = f"{type(error).__name__}: {error}"
        status = STATUS_FAILED

    result = StepResult(
        step=step,
        status=status,
        started_at=started.isoformat(),
        finished_at=utc_now().isoformat(),
        detail=detail,
    )
    record_step(connection, result)
    logger.info("Pipeline step %s -> %s (%s)", step, status, detail)
    return result


def run_pipeline(
    db_path: Path | None = None,
    catalog_path: Path = CATALOG_PATH,
    snapshot_date: date | None = None,
    reference_inbox: Path | None = None,
) -> list[StepResult]:
    """Rebuild the cleaned analysis table, then store today's market summary.

    The snapshot still runs when cleaning fails: the previous cleaned table is
    the honest state of the data, and skipping the summary would leave a hole in
    the trend series that cannot be backfilled later.
    """
    db_path = db_path or sqlite_db_path()
    repository = ListingRepository(db_path)

    def clean() -> str:
        result = clean_database(db_path, catalog_path, CleanRules())
        return f"raw_total={result.raw_total} clean_total={result.clean_total} rejected_total={result.rejected_total}"

    def snapshot() -> str:
        saved = save_snapshot(repository, snapshot_date or date.today())
        if saved == 0:
            raise RuntimeError("Snapshot icin analiz edilebilir ilan bulunamadi.")
        return f"saved_snapshots={saved}"

    def reference() -> str:
        results = import_new_files(reference_inbox or REFERENCE_INBOX, db_path)
        if not results:
            raise NothingToDo("Yeni kasko donemi bulunamadi.")
        return " ".join(str(result) for result in results)

    with closing(sqlite3.connect(db_path)) as connection:
        ensure_run_table(connection)
        return [
            run_step(connection, STEP_REFERENCE, reference),
            run_step(connection, STEP_CLEAN, clean),
            run_step(connection, STEP_SNAPSHOT, snapshot),
        ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gunluk bakim hattini calistir.")
    parser.add_argument("--db-path", type=Path, default=None)
    parser.add_argument("--catalog-path", type=Path, default=CATALOG_PATH)
    parser.add_argument("--date", type=date.fromisoformat, default=None)
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    db_path = args.db_path or sqlite_db_path()
    if not db_path.exists():
        # Creating an empty database here would only hide that ingestion never ran.
        print(
            f"Veritabani bulunamadi: {db_path}. Demo verisi icin scripts/load_demo_data, "
            "kendi verin icin scripts/import_listings calistirin."
        )
        return 1
    results = run_pipeline(db_path, args.catalog_path, args.date)
    for result in results:
        print(f"{result.step}={result.status} {result.detail}")
    return 0 if all(result.succeeded for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
