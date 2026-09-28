from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import date
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.api.database import ListingRepository
from src.api.main import app
from src.ingestion.load_listings import (
    MixedSourcesError,
    backfill_demo_snapshots,
    load_source,
    write_demo_reference_values,
)
from src.ingestion.sources.csv_file import CsvFormatError, CsvSource, parse_integer
from src.ingestion.sources.demo import DEMO_SERIES, DEMO_SOURCE, DemoConfig, DemoSource, turkish_date
from src.maintenance.clean_vehicle_data import CATALOG_PATH
from src.maintenance.pipeline import run_pipeline

REFERENCE_DATE = date(2026, 9, 28)


def _demo(count: int = 400, seed: int = 7) -> DemoSource:
    return DemoSource(DemoConfig(count=count, seed=seed), reference_date=REFERENCE_DATE)


class DemoSourceTests(unittest.TestCase):
    def test_same_seed_produces_the_same_listings(self) -> None:
        first = [(item.title, item.price, item.mileage_km) for item in _demo().listings()]
        second = [(item.title, item.price, item.mileage_km) for item in _demo().listings()]

        self.assertEqual(first, second)
        self.assertEqual(len(first), 400)

    def test_every_listing_is_marked_as_demo(self) -> None:
        self.assertEqual({item.source for item in _demo().listings()}, {DEMO_SOURCE})

    def test_demo_vehicles_exist_in_the_catalog(self) -> None:
        """The dropdowns come from the catalog; demo rows must line up with them."""
        catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        packages = {
            (brand["name"].replace(" - ", "-"), series["name"]): set(series.get("models", []))
            for brand in catalog["brands"]
            for series in brand.get("series", [])
        }
        for series in DEMO_SERIES:
            key = (series.brand, series.series)
            with self.subTest(series=key):
                self.assertIn(key, packages)
                for trim in series.trims:
                    self.assertIn(trim.package, packages[key])

    def test_newer_and_less_driven_cars_cost_more(self) -> None:
        listings = list(_demo(count=3000).listings())
        egea = [item for item in listings if item.series == "Egea" and item.model == "1.4 Fire Easy"]
        new = [item.price for item in egea if item.year >= 2024]
        old = [item.price for item in egea if item.year <= 2018]

        self.assertTrue(new and old)
        self.assertGreater(sum(new) / len(new), sum(old) / len(old))

    def test_listing_dates_use_the_format_the_trend_parser_reads(self) -> None:
        self.assertEqual(turkish_date(date(2026, 8, 3)), "3 Ağustos 2026")


class CsvSourceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _write(self, name: str, text: str) -> Path:
        path = self.root / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_turkish_number_formats_are_read(self) -> None:
        self.assertEqual(parse_integer("1.250.000 TL"), 1_250_000)
        self.assertEqual(parse_integer("85.000 km"), 85_000)
        self.assertIsNone(parse_integer(""))

    def test_semicolon_separated_export_is_imported(self) -> None:
        path = self._write(
            "partner.csv",
            "title;brand;series;model;year;mileage_km;price;city\n"
            "2020 Fiat Egea;Fiat;Egea;1.4 Fire Easy;2020;85.000 km;1.050.000 TL;Ankara\n",
        )

        listings = list(CsvSource(path).listings())

        self.assertEqual(len(listings), 1)
        self.assertEqual(listings[0].source, "partner")
        self.assertEqual(listings[0].price, 1_050_000)
        self.assertEqual(listings[0].mileage_km, 85_000)
        self.assertEqual(listings[0].city, "Ankara")

    def test_missing_required_columns_are_named_with_the_headers_found(self) -> None:
        path = self._write("broken.csv", "Marka,Fiyat\nFiat,100000\n")

        with self.assertRaises(CsvFormatError) as caught:
            list(CsvSource(path).listings())

        message = str(caught.exception)
        self.assertIn("title", message)
        self.assertIn("Marka, Fiyat", message)

    def test_unknown_columns_are_reported_not_imported(self) -> None:
        path = self._write(
            "extra.csv",
            "title,brand,series,model,year,mileage_km,price,notlar\nx,Fiat,Egea,a,2020,1,100000,hi\n",
        )
        source = CsvSource(path)
        list(source.listings())

        self.assertEqual(source.skipped_columns, ["notlar"])

    def test_reimporting_the_same_file_does_not_duplicate_rows(self) -> None:
        path = self._write(
            "same.csv",
            "title,brand,series,model,year,mileage_km,price\n2020 Fiat Egea,Fiat,Egea,a,2020,1000,900000\n",
        )
        db_path = self.root / "listings.sqlite3"

        load_source(CsvSource(path), db_path)
        load_source(CsvSource(path), db_path)

        with closing(sqlite3.connect(db_path)) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM vehicle_listings").fetchone()[0], 1)

    def test_demo_data_is_never_mixed_with_real_listings(self) -> None:
        path = self._write(
            "real.csv",
            "title,brand,series,model,year,mileage_km,price\n2020 Fiat Egea,Fiat,Egea,a,2020,1000,900000\n",
        )
        db_path = self.root / "listings.sqlite3"
        load_source(CsvSource(path), db_path)

        with self.assertRaises(MixedSourcesError):
            load_source(_demo(count=5), db_path)


class DemoEndToEndTests(unittest.TestCase):
    """The demo set must travel the real pipeline and serve the real API."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.db_path = Path(cls.temp_dir.name) / "demo.sqlite3"
        cls.load = load_source(_demo(count=1500), cls.db_path)
        cls.steps = run_pipeline(cls.db_path, snapshot_date=REFERENCE_DATE, reference_inbox=Path(cls.temp_dir.name))
        cls.snapshots = backfill_demo_snapshots(cls.db_path, REFERENCE_DATE)
        write_demo_reference_values(cls.db_path, REFERENCE_DATE)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp_dir.cleanup()

    def setUp(self) -> None:
        repository = ListingRepository(self.db_path)
        self.patches = [
            patch("src.api.main.ListingRepository", lambda *_args, **_kwargs: repository),
            patch("src.api.dependencies.REPOSITORY", repository),
        ]
        for item in self.patches:
            item.start()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        for item in self.patches:
            item.stop()

    def test_nearly_every_demo_listing_survives_cleaning(self) -> None:
        clean = {step.step: step for step in self.steps}["clean_vehicle_data"]
        with closing(sqlite3.connect(self.db_path)) as connection:
            clean_total = connection.execute("SELECT COUNT(*) FROM vehicle_listings_clean").fetchone()[0]

        self.assertEqual(clean.status, "success")
        self.assertGreater(clean_total, self.load.read * 0.95)

    def test_weekly_history_is_backfilled_for_market_movers(self) -> None:
        with closing(sqlite3.connect(self.db_path)) as connection:
            days = connection.execute("SELECT COUNT(DISTINCT snapshot_date) FROM market_price_snapshots").fetchone()[0]

        self.assertGreater(self.snapshots, 0)
        self.assertGreater(days, 2)

    def test_health_says_the_data_is_demo(self) -> None:
        body = self.client.get("/api/health").json()

        self.assertTrue(body["demo_data"])
        self.assertEqual(body["data_sources"], [DEMO_SOURCE])

    def test_valuation_works_on_demo_data(self) -> None:
        response = self.client.post(
            "/api/valuation",
            json={"brand": "Fiat", "series": "Egea", "year": 2020, "mileage_km": 90000},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertGreater(body["listing_count"], 0)
        self.assertIsNotNone(body["estimated_market_value"])
        # The kasko value shown with demo data must be labelled as demo.
        self.assertEqual(body["reference_value"]["source"], DEMO_SOURCE)
        self.assertGreater(body["reference_value"]["market_to_reference_percent"], 0)


if __name__ == "__main__":
    unittest.main()
