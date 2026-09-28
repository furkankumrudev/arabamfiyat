from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import date
from pathlib import Path

import pandas as pd

from src.analysis.market_engine import build_market_analysis
from src.api.database import DatabaseUnavailable, ListingRepository, ensure_snapshot_table
from src.api.dependencies import MarketFilters
from src.api.routes.market import get_movers, get_overview, get_trend
from src.api.routes.valuation import create_valuation
from src.api.schemas import ValuationRequest
from src.api.services.market_service import (
    _snapshot_scope,
    build_price_relationships,
    build_reference_listing_trend,
    build_reference_mileage_points,
    build_reference_price_points,
    condition_adjustment_from_payload,
    enrich_condition_payload,
    grouped_table,
)
from src.api.services.trend_service import build_listing_trend
from src.maintenance.save_market_snapshot import save_snapshot


class ApiServiceTests(unittest.TestCase):
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
                """INSERT INTO vehicle_listings_clean VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    (1, "Test Sedan", "Test", "A", "1.0", 2020, 80000, "Otomatik", "Benzin", "Sedan", "Ankara", 900000, "TRY", "1 Temmuz 2026", "https://example.test/1", None, "2026-07-01T12:00:00", 1),
                    (2, "Test Sedan", "Test", "A", "1.0", 2021, 65000, "Otomatik", "Benzin", "Sedan", "Ankara", 1000000, "TRY", "2 Temmuz 2026", "https://example.test/2", None, "2026-07-02T12:00:00", 0),
                ],
            )
            connection.commit()
        self.repository = ListingRepository(self.db_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_trend_uses_real_listing_dates(self) -> None:
        frame = pd.DataFrame({"listing_date": ["1 Temmuz 2026", "2 Temmuz 2026"], "price": [900000, 1000000]})
        trend = build_listing_trend(frame)
        self.assertEqual(len(trend), 2)
        self.assertEqual(trend[0]["median_price"], 900000.0)

    def test_weekly_trend_takes_the_median_of_the_weeks_listings(self) -> None:
        # 28 Eylül 2026 is a Monday; the first three dates share its week.
        frame = pd.DataFrame({
            "listing_date": ["28 Eylül 2026", "29 Eylül 2026", "30 Eylül 2026", "5 Ekim 2026"],
            "price": [100, 900, 1000, 500],
        })
        trend = build_listing_trend(frame, interval="week")
        self.assertEqual([str(point["date"]) for point in trend], ["2026-09-28", "2026-10-05"])
        self.assertEqual(trend[0]["median_price"], 900.0)
        self.assertEqual(trend[0]["listing_count"], 3)

    def test_overview_and_empty_history_are_honest(self) -> None:
        overview = get_overview(MarketFilters(), self.repository)
        self.assertEqual(overview.listing_count, 2)
        self.assertIsNone(overview.change_30d)

        trend = get_trend(MarketFilters(), None, None, self.repository)
        self.assertTrue(trend.available)

        movers = get_movers("down", self.repository)
        self.assertFalse(movers.available)

    def test_valuation_returns_low_sample_not_fake_price(self) -> None:
        response = create_valuation(
            ValuationRequest(brand="Test", series="A", model="1.0", year=2020, mileage_km=80000),
            self.repository,
        )
        self.assertEqual(response.status, "low_sample")
        self.assertEqual(response.listing_count, 1)
        self.assertEqual(response.comparison_summary.matched_listing_count, 2)
        self.assertEqual(response.comparison_summary.used_listing_count, 1)

    def test_clean_only_valuation_uses_clean_claimed_listings(self) -> None:
        response = create_valuation(
            ValuationRequest(brand="Test", series="A", model="1.0", clean_only=True),
            self.repository,
        )
        self.assertEqual(response.status, "low_sample")
        self.assertEqual(response.listing_count, 1)
        self.assertTrue(response.comparison_summary.clean_only)

    def test_missing_database_is_reported(self) -> None:
        missing = ListingRepository(Path(self.temp_dir.name) / "missing.sqlite3")
        with self.assertRaises(DatabaseUnavailable):
            missing.listing_count()

    def test_repository_falls_back_to_raw_table_when_clean_table_is_empty(self) -> None:
        with closing(self.repository.connect()) as connection:
            connection.execute("DELETE FROM vehicle_listings_clean")
            connection.execute(
                """CREATE TABLE vehicle_listings (
                    id INTEGER PRIMARY KEY, title TEXT, brand TEXT, series TEXT, model TEXT,
                    year INTEGER, mileage_km INTEGER, price INTEGER
                )"""
            )
            connection.execute(
                """INSERT INTO vehicle_listings
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (1, "Ham ilan", "Test", "A", "1.0", 2020, 80_000, 900_000),
            )
            connection.commit()

        self.assertEqual(self.repository.listing_table(), "vehicle_listings")
        self.assertEqual(self.repository.listing_count(), 1)

    def test_snapshot_save_is_idempotent_for_one_day(self) -> None:
        snapshot_date = date(2026, 7, 23)
        self.assertEqual(save_snapshot(self.repository, snapshot_date), 1)
        self.assertEqual(save_snapshot(self.repository, snapshot_date), 1)
        with closing(self.repository.connect()) as connection:
            count = connection.execute("SELECT COUNT(*) FROM market_price_snapshots").fetchone()[0]
        self.assertEqual(count, 1)

    def test_snapshot_scope_never_uses_market_change_for_a_narrow_filter(self) -> None:
        self.assertEqual(_snapshot_scope({}), ("market", "all"))
        self.assertEqual(_snapshot_scope({"brand": "Test"}), ("brand", "Test"))
        self.assertIsNone(_snapshot_scope({"brand": "Test", "year_min": 2020}))

    def _brand_snapshot(self, day: str, median: float) -> None:
        with closing(self.repository.connect()) as connection:
            ensure_snapshot_table(connection)
            connection.execute(
                """INSERT INTO market_price_snapshots (snapshot_date, dimension_type, dimension_value, dimension_key,
                    brand, average_price, median_price, listing_count) VALUES (?, 'brand', 'Test', 'brand:test', 'Test', ?, ?, 10)""",
                (day, median, median),
            )
            connection.commit()

    def test_entered_damage_is_never_dropped_silently(self) -> None:
        payload = {"brand": "Test", "series": "A", "model": None, "year": 2020, "mileage_km": 80000,
                   "changed_parts": 2, "painted_parts": 1}
        adjustment, note = condition_adjustment_from_payload(payload)

        self.assertIsNone(adjustment)
        self.assertIn("hesaplanamadı", note)

    def test_missing_package_falls_back_to_the_groups_most_common_one(self) -> None:
        listings = pd.DataFrame({"year": [2020, 2021, 2020], "mileage_km": [1, 2, 3], "model": ["1.0", "1.4", "1.0"]})
        enriched, note = enrich_condition_payload({"changed_parts": 1, "painted_parts": 0}, listings)

        self.assertEqual(enriched["model"], "1.0")
        self.assertIn("en sık görülen paket", note)

    def test_brand_table_reports_snapshot_changes(self) -> None:
        self._brand_snapshot("2026-06-01", 800000)
        self._brand_snapshot("2026-07-01", 880000)

        row = grouped_table(self.repository, {}, "brand")[0]

        self.assertEqual(row["label"], "Test")
        self.assertAlmostEqual(row["change_30d"], 10.0)
        self.assertIsNone(row["change_90d"])

    def test_brand_table_hides_changes_that_do_not_match_the_filters(self) -> None:
        self._brand_snapshot("2026-06-01", 800000)
        self._brand_snapshot("2026-07-01", 880000)

        filtered = grouped_table(self.repository, {"year_min": 2021}, "brand")[0]
        by_fuel = grouped_table(self.repository, {}, "fuel_type")[0]

        self.assertIsNone(filtered["change_30d"])
        self.assertIsNone(by_fuel["change_30d"])

    def test_price_relationships_use_real_years_and_mileage_bands(self) -> None:
        frame = pd.DataFrame({
            "year": [2020, 2020, 2020, 2021, 2021, 2021],
            "mileage_km": [20_000, 25_000, 22_000, 80_000, 90_000, 95_000],
            "price": [900_000, 920_000, 910_000, 1_000_000, 1_020_000, 980_000],
        })
        result = build_price_relationships(frame)
        self.assertEqual([point["label"] for point in result["year_points"]], ["2020", "2021"])
        self.assertEqual(result["mileage_points"][0]["label"], "0-25 bin km")
        self.assertEqual(result["mileage_points"][0]["listing_count"], 3)

    def test_reference_price_points_keep_each_comparable_listing(self) -> None:
        frame = pd.DataFrame({"price": [900_000, 950_000, 1_000_000, 1_050_000, 1_100_000]})
        points = build_reference_price_points(frame)
        self.assertEqual(len(points), len(frame))
        self.assertEqual(points[0]["price"], 900_000)
        self.assertEqual(points[-1]["price"], 1_100_000)

    def test_reference_charts_use_only_the_selected_listing_group(self) -> None:
        frame = pd.DataFrame({
            "mileage_km": [60_000, 70_000, 80_000, 90_000],
            "price": [1_200_000, 1_150_000, 1_100_000, 1_050_000],
            "listing_date": ["1 Temmuz 2026", "1 Temmuz 2026", "2 Temmuz 2026", "2 Temmuz 2026"],
        })
        mileage_points = build_reference_mileage_points(frame)
        date_points = build_reference_listing_trend(frame)
        self.assertEqual(sum(point["listing_count"] for point in mileage_points), 4)
        self.assertEqual(len(date_points), 2)
        self.assertEqual(date_points[0]["median_price"], 1_175_000.0)

    def test_condition_payload_uses_reference_medians_when_year_and_mileage_are_blank(self) -> None:
        frame = pd.DataFrame({"year": [2020, 2022], "mileage_km": [50_000, 90_000]})
        enriched, note = enrich_condition_payload(
            {"brand": "Test", "changed_parts": 2, "painted_parts": 0}, frame,
        )
        self.assertEqual(enriched["year"], 2021)
        self.assertEqual(enriched["mileage_km"], 70_000)
        self.assertIn("Model yılı", note)

    def test_market_analysis_uses_all_matches_inside_the_context_window(self) -> None:
        frame = pd.DataFrame({
            "price": [900_000 + index * 10_000 for index in range(8)],
            "year": [2020, 2020, 2020, 2020, 2020, 2020, 2019, 2024],
            "mileage_km": [80_000, 85_000, 90_000, 95_000, 75_000, 70_000, 80_000, 80_000],
            "model": ["1.0"] * 8,
            "title": ["Test"] * 8,
        })
        broad = build_market_analysis(frame, selected_model="1.0")
        targeted = build_market_analysis(frame, selected_model="1.0", target_year=2020, target_mileage=80_000)
        self.assertEqual(broad["selected_count"], 8)
        self.assertEqual(targeted["selected_count"], 6)
        self.assertIn("2020 model yılı", targeted["selection_note"])
        self.assertIn("55.000-105.000 km", targeted["selection_note"])

    def test_market_analysis_does_not_substitute_distant_mileage(self) -> None:
        frame = pd.DataFrame({
            "price": [900_000, 920_000],
            "year": [2020, 2021],
            "mileage_km": [250_000, 270_000],
            "model": ["1.0", "1.0"],
            "title": ["Test", "Test"],
        })
        result = build_market_analysis(frame, selected_model="1.0", target_year=2020, target_mileage=80_000)
        self.assertEqual(result["status"], "empty")
        self.assertEqual(result["selected_count"], 0)
        self.assertIn("55.000-105.000 km", result["selection_note"])


if __name__ == "__main__":
    unittest.main()
