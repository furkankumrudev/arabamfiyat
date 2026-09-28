from __future__ import annotations

import sqlite3
import unittest
from contextlib import closing

from src.api.services.reference_service import MATCH_MODEL, MATCH_SERIES, lookup_reference_value
from src.ingestion.tsb_reference import REFERENCE_TABLE, SOURCE_TSB, ensure_reference_table

ROWS = [
    (SOURCE_TSB, "2026-09", "FIAT", "EGEA 1.4 FIRE EASY", 2020, 900_000),
    (SOURCE_TSB, "2026-09", "FIAT", "EGEA 1.6 MULTIJET LOUNGE", 2020, 1_100_000),
    (SOURCE_TSB, "2026-09", "FIAT", "EGEA 1.3 MULTIJET URBAN", 2020, 1_000_000),
    (SOURCE_TSB, "2026-08", "FIAT", "EGEA 1.4 FIRE EASY", 2020, 850_000),
    (SOURCE_TSB, "2026-09", "BMW", "320I M SPORT", 2021, 3_000_000),
    (SOURCE_TSB, "2026-09", "BMW", "520I LUXURY LINE", 2021, 4_500_000),
    (SOURCE_TSB, "2026-09", "MERCEDES-BENZ", "C 200 AMG", 2021, 3_500_000),
    ("demo", "2026-10", "FIAT", "EGEA 1.4 FIRE EASY", 2020, 1),
]


class ReferenceLookupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = sqlite3.connect(":memory:")
        ensure_reference_table(self.connection)
        self.connection.executemany(
            f"""INSERT INTO {REFERENCE_TABLE} (source, period, brand, model_name, model_year, reference_value, loaded_at)
                VALUES (?, ?, ?, ?, ?, ?, 'now')""",
            ROWS,
        )

    def tearDown(self) -> None:
        self.connection.close()

    def lookup(self, brand: str, series: str, model: str | None, year: int | None):
        return lookup_reference_value(self.connection, brand, series, model, year)

    def test_matching_package_uses_its_own_value_from_the_latest_official_period(self) -> None:
        result = self.lookup("Fiat", "Egea", "1.4 Fire Easy", 2020)

        self.assertEqual(result["match"], MATCH_MODEL)
        self.assertEqual(result["value"], 900_000)
        self.assertEqual(result["period"], "2026-09")
        self.assertEqual(result["source"], SOURCE_TSB)

    def test_unknown_package_falls_back_to_the_series_median_and_says_so(self) -> None:
        result = self.lookup("Fiat", "Egea", "1.0 Firefly Lounge", 2020)

        self.assertEqual(result["match"], MATCH_SERIES)
        self.assertEqual(result["value"], 1_000_000)
        self.assertEqual(result["candidate_count"], 3)
        self.assertIsNone(result["matched_name"])

    def test_numeric_series_matches_model_codes(self) -> None:
        result = self.lookup("BMW", "3 Serisi", "320i M Sport", 2021)

        self.assertEqual(result["match"], MATCH_MODEL)
        self.assertEqual(result["value"], 3_000_000)
        self.assertEqual(self.lookup("BMW", "3 Serisi", None, 2021)["candidate_count"], 1)

    def test_brand_spelling_differences_are_tolerated(self) -> None:
        self.assertIsNotNone(self.lookup("Mercedes - Benz", "C Serisi", None, 2021))

    def test_no_year_or_no_match_returns_nothing_rather_than_a_guess(self) -> None:
        self.assertIsNone(self.lookup("Fiat", "Egea", None, None))
        self.assertIsNone(self.lookup("Fiat", "Egea", None, 1995))
        self.assertIsNone(self.lookup("Renault", "Clio", None, 2020))

    def test_missing_table_is_not_an_error(self) -> None:
        with closing(sqlite3.connect(":memory:")) as empty:
            self.assertIsNone(lookup_reference_value(empty, "Fiat", "Egea", None, 2020))


if __name__ == "__main__":
    unittest.main()
