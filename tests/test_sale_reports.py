from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.api.main import app
from src.api.services.sale_reports import MIN_REPORTS_TO_SHOW, save_report, summarize_reports

REPORT = {"brand": "Fiat", "series": "Egea", "model": "1.4 Fire Easy", "year": 2020, "mileage_km": 90000,
          "sale_price": 950000, "sold_month": "2026-09", "city": "Ankara"}


class SaleReportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "sale_reports.sqlite3"
        self.patch = patch("src.api.routes.sale_reports.sale_reports_db_path", lambda: self.db_path)
        self.patch.start()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.patch.stop()
        self.temp_dir.cleanup()

    def test_a_report_is_saved_through_the_api(self) -> None:
        response = self.client.post("/api/sale-reports", json=REPORT)

        self.assertEqual(response.status_code, 201)
        self.assertEqual(summarize_reports(self.db_path, "Fiat", "Egea", 2020)["count"], 1)

    def test_implausible_reports_are_rejected(self) -> None:
        for change in ({"sale_price": 5}, {"year": 1800}, {"sold_month": "2026-13"}, {"brand": ""}):
            with self.subTest(change=change):
                self.assertEqual(self.client.post("/api/sale-reports", json={**REPORT, **change}).status_code, 422)

    def test_median_stays_hidden_until_enough_reports_agree(self) -> None:
        for price in (900_000, 1_000_000):
            save_report(self.db_path, {**REPORT, "sale_price": price})
        few = summarize_reports(self.db_path, "fiat", "egea", 2020)
        self.assertEqual(few["count"], 2)
        self.assertIsNone(few["median_price"])

        save_report(self.db_path, {**REPORT, "sale_price": 1_100_000, "year": 2021})
        enough = summarize_reports(self.db_path, "Fiat", "Egea", 2020)
        self.assertEqual(enough["count"], MIN_REPORTS_TO_SHOW)
        self.assertEqual(enough["median_price"], 1_000_000)

    def test_other_years_and_vehicles_do_not_count(self) -> None:
        save_report(self.db_path, {**REPORT, "year": 2015})
        save_report(self.db_path, {**REPORT, "series": "Linea"})
        self.assertEqual(summarize_reports(self.db_path, "Fiat", "Egea", 2020)["count"], 0)

    def test_no_database_yet_means_no_summary(self) -> None:
        self.assertIsNone(summarize_reports(self.db_path, "Fiat", "Egea", 2020))


if __name__ == "__main__":
    unittest.main()
