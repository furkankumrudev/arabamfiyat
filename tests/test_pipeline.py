from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from src.api.main import pipeline_freshness
from src.maintenance.pipeline import (
    RUN_TABLE,
    STATUS_FAILED,
    STATUS_SKIPPED,
    STATUS_SUCCESS,
    STEP_CLEAN,
    STEP_REFERENCE,
    STEP_SNAPSHOT,
    NothingToDo,
    StepResult,
    ensure_run_table,
    last_success_at,
    main,
    record_step,
    run_step,
)
from src.maintenance.scheduler import seconds_until_next_run


def _result(step: str, status: str, finished_at: str) -> StepResult:
    return StepResult(
        step=step, status=status, started_at=finished_at, finished_at=finished_at, detail="test"
    )


class PipelineEntryPointTests(unittest.TestCase):
    def test_missing_database_is_reported_instead_of_created(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "runtime" / "vehicle_listings.sqlite3"
            self.assertEqual(main(["--db-path", str(db_path)]), 1)
            self.assertFalse(db_path.exists())


class PipelineRunLogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "runs.sqlite3"
        self.connection = sqlite3.connect(self.db_path)
        ensure_run_table(self.connection)

    def tearDown(self) -> None:
        self.connection.close()
        self.temp_dir.cleanup()

    def test_run_table_creation_is_idempotent(self) -> None:
        ensure_run_table(self.connection)
        ensure_run_table(self.connection)
        tables = {
            row[0]
            for row in self.connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        self.assertIn(RUN_TABLE, tables)

    def test_no_successful_run_reports_nothing_rather_than_a_guess(self) -> None:
        self.assertIsNone(last_success_at(self.connection))

    def test_missing_table_is_reported_as_no_run(self) -> None:
        with closing(sqlite3.connect(":memory:")) as fresh:
            self.assertIsNone(last_success_at(fresh))

    def test_one_successful_step_does_not_count_as_a_successful_pipeline(self) -> None:
        record_step(self.connection, _result(STEP_CLEAN, STATUS_SUCCESS, "2026-09-20T03:00:00+00:00"))
        self.assertIsNone(last_success_at(self.connection))
        self.assertEqual(last_success_at(self.connection, STEP_CLEAN), "2026-09-20T03:00:00+00:00")

    def test_pipeline_freshness_follows_the_lagging_step(self) -> None:
        record_step(self.connection, _result(STEP_CLEAN, STATUS_SUCCESS, "2026-09-21T03:00:00+00:00"))
        record_step(self.connection, _result(STEP_SNAPSHOT, STATUS_SUCCESS, "2026-09-19T03:05:00+00:00"))
        self.assertEqual(last_success_at(self.connection), "2026-09-19T03:05:00+00:00")

    def test_failed_runs_never_count_as_success(self) -> None:
        record_step(self.connection, _result(STEP_CLEAN, STATUS_SUCCESS, "2026-09-21T03:00:00+00:00"))
        record_step(self.connection, _result(STEP_SNAPSHOT, STATUS_FAILED, "2026-09-21T03:05:00+00:00"))
        self.assertIsNone(last_success_at(self.connection))

    def test_a_failing_step_is_recorded_instead_of_raising(self) -> None:
        def explode() -> str:
            raise RuntimeError("kaynak yok")

        result = run_step(self.connection, STEP_CLEAN, explode)

        self.assertFalse(result.succeeded)
        self.assertIn("kaynak yok", result.detail)
        stored = self.connection.execute(
            f"SELECT status, detail FROM {RUN_TABLE} WHERE step = ?", (STEP_CLEAN,)
        ).fetchone()
        self.assertEqual(stored[0], STATUS_FAILED)

    def test_a_step_with_no_work_is_skipped_not_failed(self) -> None:
        def nothing_new() -> str:
            raise NothingToDo("Yeni kasko donemi bulunamadi.")

        result = run_step(self.connection, STEP_REFERENCE, nothing_new)

        self.assertEqual(result.status, STATUS_SKIPPED)
        # The monthly list has nothing new on most days; that must not make the
        # daily pipeline look broken.
        self.assertTrue(result.succeeded)

    def test_a_skipped_step_does_not_count_as_pipeline_freshness(self) -> None:
        record_step(self.connection, _result(STEP_REFERENCE, STATUS_SKIPPED, "2026-09-21T03:00:00+00:00"))

        self.assertIsNone(last_success_at(self.connection))

    def test_a_successful_step_records_its_detail(self) -> None:
        result = run_step(self.connection, STEP_SNAPSHOT, lambda: "saved_snapshots=4")

        self.assertTrue(result.succeeded)
        self.assertEqual(result.detail, "saved_snapshots=4")


class PipelineFreshnessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = sqlite3.connect(":memory:")
        ensure_run_table(self.connection)

    def tearDown(self) -> None:
        self.connection.close()

    def _record_pipeline_success(self, finished: datetime) -> None:
        stamp = finished.isoformat()
        record_step(self.connection, _result(STEP_CLEAN, STATUS_SUCCESS, stamp))
        record_step(self.connection, _result(STEP_SNAPSHOT, STATUS_SUCCESS, stamp))

    def test_recent_run_is_not_stale(self) -> None:
        self._record_pipeline_success(datetime.now(UTC) - timedelta(hours=2))
        freshness = pipeline_freshness(self.connection)
        self.assertFalse(freshness["pipeline_stale"])
        self.assertAlmostEqual(float(freshness["pipeline_age_hours"]), 2.0, places=1)

    def test_a_stopped_pipeline_is_reported_as_stale(self) -> None:
        self._record_pipeline_success(datetime.now(UTC) - timedelta(days=3))
        freshness = pipeline_freshness(self.connection)
        self.assertTrue(freshness["pipeline_stale"])

    def test_missing_history_leaves_staleness_unknown_instead_of_false(self) -> None:
        freshness = pipeline_freshness(self.connection)
        self.assertIsNone(freshness["pipeline_stale"])
        self.assertIsNone(freshness["last_pipeline_success_at"])

    def test_naive_timestamps_are_read_as_utc(self) -> None:
        naive = (datetime.now(UTC) - timedelta(hours=1)).replace(tzinfo=None)
        self._record_pipeline_success(naive)
        freshness = pipeline_freshness(self.connection)
        self.assertAlmostEqual(float(freshness["pipeline_age_hours"]), 1.0, places=1)

    def test_unreadable_timestamp_does_not_break_the_health_check(self) -> None:
        with patch("src.api.main.last_success_at", return_value="not-a-timestamp"):
            freshness = pipeline_freshness(self.connection)
        self.assertEqual(freshness["last_pipeline_success_at"], "not-a-timestamp")
        self.assertIsNone(freshness["pipeline_stale"])


class SchedulerTimingTests(unittest.TestCase):
    def test_target_later_today(self) -> None:
        now = datetime(2026, 9, 21, 1, 0, tzinfo=UTC)
        self.assertEqual(seconds_until_next_run(now, 3, 0), 2 * 3600)

    def test_target_already_passed_rolls_to_tomorrow(self) -> None:
        now = datetime(2026, 9, 21, 5, 0, tzinfo=UTC)
        self.assertEqual(seconds_until_next_run(now, 3, 0), 22 * 3600)

    def test_a_restart_during_the_scheduled_minute_waits_a_full_day(self) -> None:
        now = datetime(2026, 9, 21, 3, 0, tzinfo=UTC)
        self.assertEqual(seconds_until_next_run(now, 3, 0), 24 * 3600)

    def test_midnight_target_is_handled(self) -> None:
        now = datetime(2026, 9, 21, 23, 30, tzinfo=UTC)
        self.assertEqual(seconds_until_next_run(now, 0, 0), 30 * 60)

    def test_invalid_schedule_is_rejected(self) -> None:
        now = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)
        with self.assertRaises(ValueError):
            seconds_until_next_run(now, 24, 0)
        with self.assertRaises(ValueError):
            seconds_until_next_run(now, 3, 60)


if __name__ == "__main__":
    unittest.main()
