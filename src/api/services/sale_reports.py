"""Sale prices that users report for their own cars.

A reported sale price is what a car actually sold for, which listings cannot
tell. Reports are kept in their own database and never mixed into the listing
tables; the valuation only shows their median once enough of them agree on
the same vehicle, so a single report can neither identify a person nor skew
the answer.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from typing import Any

TABLE = "user_sale_reports"
# Below this many reports the median is not shown at all.
MIN_REPORTS_TO_SHOW = 3
YEAR_WINDOW = 1


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.execute(
        f"""CREATE TABLE IF NOT EXISTS {TABLE} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            brand TEXT NOT NULL,
            series TEXT NOT NULL,
            model TEXT,
            year INTEGER NOT NULL,
            mileage_km INTEGER,
            sale_price INTEGER NOT NULL,
            sold_month TEXT,
            city TEXT,
            changed_parts INTEGER,
            painted_parts INTEGER,
            created_at TEXT NOT NULL
        )"""
    )
    connection.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE}_vehicle ON {TABLE}(brand, series, year)")
    return connection


def save_report(db_path: Path, report: dict[str, Any]) -> int:
    with closing(_connect(db_path)) as connection:
        cursor = connection.execute(
            f"""INSERT INTO {TABLE} (brand, series, model, year, mileage_km, sale_price, sold_month, city,
                changed_parts, painted_parts, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                report["brand"].strip(), report["series"].strip(), (report.get("model") or "").strip() or None,
                int(report["year"]), report.get("mileage_km"), int(report["sale_price"]), report.get("sold_month"),
                (report.get("city") or "").strip() or None, report.get("changed_parts"), report.get("painted_parts"),
                datetime.now(UTC).isoformat(),
            ),
        )
        connection.commit()
        return int(cursor.lastrowid)


def summarize_reports(db_path: Path, brand: str | None, series: str | None, year: int | None) -> dict[str, Any] | None:
    """Median reported sale price for the same brand and series within a year of ``year``."""
    if not brand or not series or year is None or not db_path.exists():
        return None
    with closing(_connect(db_path)) as connection:
        prices = [
            int(row[0])
            for row in connection.execute(
                f"""SELECT sale_price FROM {TABLE}
                    WHERE LOWER(brand) = LOWER(?) AND LOWER(series) = LOWER(?) AND year BETWEEN ? AND ?""",
                (brand.strip(), series.strip(), int(year) - YEAR_WINDOW, int(year) + YEAR_WINDOW),
            )
        ]
    if len(prices) < MIN_REPORTS_TO_SHOW:
        return {"count": len(prices), "median_price": None, "year_window": YEAR_WINDOW}
    return {"count": len(prices), "median_price": float(median(prices)), "year_window": YEAR_WINDOW}
