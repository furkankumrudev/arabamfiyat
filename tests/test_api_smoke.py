"""End-to-end checks that exercise the app through real HTTP requests.

These exist because a module-level import error in any route file breaks every
endpoint at startup while unit tests that import only one service keep passing.
"""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.api.database import ListingRepository
from src.api.main import app
from src.maintenance.pipeline import (
    STATUS_SUCCESS,
    STEP_CLEAN,
    STEP_SNAPSHOT,
    StepResult,
    ensure_run_table,
    record_step,
)

ROWS = [
    (1, "Test Sedan", "Test", "A", "1.0", 2020, 80000, "Otomatik", "Benzin", "Sedan", "Ankara",
     900000, "TRY", "1 Temmuz 2026", "https://example.test/1", None, "2026-07-01T12:00:00", 1),
    (2, "Test Sedan", "Test", "A", "1.0", 2021, 65000, "Otomatik", "Benzin", "Sedan", "Ankara",
     1000000, "TRY", "2 Temmuz 2026", "https://example.test/2", None, "2026-07-02T12:00:00", 0),
]


class ApiSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "listings.sqlite3"
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                """CREATE TABLE vehicle_listings_clean (
                    id INTEGER PRIMARY KEY, title TEXT, brand TEXT, series TEXT, model TEXT,
                    year INTEGER, mileage_km INTEGER, transmission TEXT, fuel_type TEXT,
                    body_type TEXT, city TEXT, price INTEGER, currency TEXT,
                    listing_date TEXT, listing_url TEXT, image_url TEXT, scraped_at TEXT,
                    is_clean_claimed INTEGER
                )"""
            )
            connection.executemany(
                "INSERT INTO vehicle_listings_clean VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                ROWS,
            )
            connection.commit()

        self.repository = ListingRepository(self.db_path)
        # Both the health endpoint and the route dependencies must read the
        # temporary database instead of the developer's real one.
        self.patches = [
            patch("src.api.main.ListingRepository", lambda *_args, **_kwargs: self.repository),
            patch("src.api.dependencies.REPOSITORY", self.repository),
        ]
        for item in self.patches:
            item.start()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        for item in self.patches:
            item.stop()
        self.temp_dir.cleanup()

    def _record_pipeline_success(self, finished: datetime) -> None:
        stamp = finished.isoformat()
        with closing(sqlite3.connect(self.db_path)) as connection:
            ensure_run_table(connection)
            for step in (STEP_CLEAN, STEP_SNAPSHOT):
                record_step(
                    connection,
                    StepResult(step=step, status=STATUS_SUCCESS, started_at=stamp, finished_at=stamp, detail="test"),
                )

    def test_health_reports_the_listing_table(self) -> None:
        body = self.client.get("/api/health").json()

        self.assertEqual(body["status"], "ok")
        self.assertTrue(body["database_available"])
        self.assertEqual(body["table"], "vehicle_listings_clean")
        self.assertEqual(body["listing_count"], 2)

    def test_health_is_ok_without_pipeline_history_but_reports_it_as_unknown(self) -> None:
        body = self.client.get("/api/health").json()

        self.assertEqual(body["status"], "ok")
        self.assertIsNone(body["last_pipeline_success_at"])
        self.assertIsNone(body["pipeline_stale"])

    def test_health_degrades_when_the_pipeline_stopped_running(self) -> None:
        self._record_pipeline_success(datetime.now(UTC) - timedelta(days=4))

        body = self.client.get("/api/health").json()

        self.assertEqual(body["status"], "degraded")
        self.assertTrue(body["pipeline_stale"])
        self.assertGreater(body["pipeline_age_hours"], 36)

    def test_health_stays_ok_while_the_pipeline_keeps_up(self) -> None:
        self._record_pipeline_success(datetime.now(UTC) - timedelta(hours=5))

        body = self.client.get("/api/health").json()

        self.assertEqual(body["status"], "ok")
        self.assertFalse(body["pipeline_stale"])

    def test_every_route_module_is_reachable(self) -> None:
        """Guards against an import-time break in any one route file."""
        for path in ("/api/catalog/brands", "/api/market/overview", "/api/market/trend"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200, path)

    def test_catalog_brands_returns_the_seeded_brand(self) -> None:
        items = self.client.get("/api/catalog/brands").json()["items"]

        self.assertIn("Test", [item["name"] for item in items])

    def test_valuation_answers_a_real_request(self) -> None:
        response = self.client.post(
            "/api/valuation", json={"brand": "Test", "series": "A", "year": 2020, "mileage_km": 80000}
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("status", response.json())

    def test_valuation_lists_the_listings_it_rests_on(self) -> None:
        body = self.client.post(
            "/api/valuation", json={"brand": "Test", "series": "A", "year": 2020, "mileage_km": 80000}
        ).json()

        self.assertTrue(body["comparable_listings"])
        self.assertEqual(body["comparable_listings"][0]["brand"], "Test")


if __name__ == "__main__":
    unittest.main()
