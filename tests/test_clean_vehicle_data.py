from __future__ import annotations

import sqlite3
import unittest
from datetime import date

from src.maintenance.clean_vehicle_data import (
    DEFAULT_MIN_PRICE,
    CleanRules,
    ModelOutlierPolicy,
    default_max_year,
    extreme_model_price_outlier_ids,
    standardize_cosmetic_name_variants,
)


class CleanRulesDefaultTests(unittest.TestCase):
    """The scheduled pipeline builds CleanRules without arguments."""

    def test_rules_are_usable_without_arguments(self) -> None:
        rules = CleanRules()

        self.assertEqual(rules.min_price, DEFAULT_MIN_PRICE)
        self.assertEqual(rules.max_year, default_max_year())

    def test_upper_model_year_follows_the_calendar(self) -> None:
        # A hardcoded bound would reject every listing once the year rolls over.
        self.assertEqual(default_max_year(), date.today().year + 1)

    def test_explicit_arguments_still_win(self) -> None:
        rules = CleanRules(min_price=1, max_price=2, min_year=3, max_year=4, max_mileage=5)

        self.assertEqual((rules.min_price, rules.max_year), (1, 4))


class CleanVehicleDataTests(unittest.TestCase):
    def test_extreme_model_price_outlier_requires_a_large_reference_group(self) -> None:
        rows = [
            {"id": index, "brand": "Test", "series": "A", "model": "1.0", "price": 100_000 + (index % 5) * 10_000}
            for index in range(1, 51)
        ]
        rows.append({"id": 51, "brand": "Test", "series": "A", "model": "1.0", "price": 3_000_000})

        self.assertEqual(extreme_model_price_outlier_ids(rows), {51})

    def test_plausible_premium_and_small_groups_are_not_rejected(self) -> None:
        large_group = [
            {"id": index, "brand": "Test", "series": "A", "model": "1.0", "price": 100_000}
            for index in range(1, 51)
        ]
        large_group.append({"id": 51, "brand": "Test", "series": "A", "model": "1.0", "price": 1_000_000})
        small_group = [
            {"id": 100 + index, "brand": "Test", "series": "B", "model": "2.0", "price": 100_000}
            for index in range(48)
        ]
        small_group.append({"id": 200, "brand": "Test", "series": "B", "model": "2.0", "price": 5_000_000})

        self.assertEqual(extreme_model_price_outlier_ids(large_group + small_group), set())

    def test_outlier_policy_keeps_its_thresholds_together(self) -> None:
        policy = ModelOutlierPolicy(min_group_size=10, median_multiplier=12.0, iqr_multiplier=2.0)

        self.assertEqual(policy.min_group_size, 10)
        self.assertEqual(policy.upper_price_bound([100, 100, 100, 100]), 1_200.0)

    def test_cosmetic_name_variants_are_merged_without_touching_plus_packages(self) -> None:
        with sqlite3.connect(":memory:") as connection:
            connection.execute("CREATE TABLE vehicle_listings_clean (series TEXT, model TEXT)")
            connection.executemany(
                "INSERT INTO vehicle_listings_clean (series, model) VALUES (?, ?)",
                [
                    ("i30", "1.6 TDCi Titanium"),
                    ("I30", "1.6 TDCI Titanium"),
                    ("i30", "200 AMG"),
                    ("i30", "200 AMG+"),
                ],
            )

            updated = standardize_cosmetic_name_variants(connection, ["series", "model"])

            self.assertEqual(updated, {"series": 1, "model": 1})
            self.assertEqual(
                connection.execute(
                    "SELECT DISTINCT series FROM vehicle_listings_clean ORDER BY series"
                ).fetchall(),
                [("i30",)],
            )
            models = [
                row[0]
                for row in connection.execute(
                    "SELECT DISTINCT model FROM vehicle_listings_clean ORDER BY model"
                )
            ]
            self.assertEqual(len(models), 3)
            self.assertEqual(sum("tdci titanium" in model.casefold() for model in models), 1)
            self.assertIn("200 AMG", models)
            self.assertIn("200 AMG+", models)


if __name__ == "__main__":
    unittest.main()
