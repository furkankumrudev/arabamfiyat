"""Real listing-date aggregations and true snapshot-based change calculations."""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta

import pandas as pd

from ..database import SNAPSHOT_TABLE
from ..listing_dates import TURKISH_MONTHS, parse_listing_date, parse_listing_dates

__all__ = ["TURKISH_MONTHS", "build_listing_trend", "parse_listing_date", "snapshot_changes"]


def build_listing_trend(
    listings: pd.DataFrame,
    start_date: date | None = None,
    end_date: date | None = None,
    interval: str = "day",
) -> list[dict[str, object]]:
    """Median and mean asking price per listing day, or per week starting Monday.

    Weekly points are computed from the listings themselves, not from daily
    medians, so a week's median is a true median.
    """
    if listings.empty or "listing_date" not in listings:
        return []
    frame = listings[[column for column in ("price", "listing_date", "parsed_listing_date") if column in listings]].copy()
    # The repository parses dates once per database version; reuse that when present.
    if "parsed_listing_date" in frame:
        frame["date"] = pd.to_datetime(frame["parsed_listing_date"], errors="coerce")
    else:
        frame["date"] = parse_listing_dates(frame["listing_date"])
    frame = frame.dropna(subset=["date", "price"])
    if start_date:
        frame = frame[frame["date"] >= pd.Timestamp(start_date)]
    if end_date:
        frame = frame[frame["date"] <= pd.Timestamp(end_date)]
    if frame.empty:
        return []
    if interval == "week":
        frame["date"] = frame["date"] - pd.to_timedelta(frame["date"].dt.weekday, unit="D")
    grouped = frame.groupby("date", as_index=False).agg(
        median_price=("price", "median"), average_price=("price", "mean"), listing_count=("price", "count")
    )
    return [
        {
            "date": row.date.date(), "median_price": float(row.median_price),
            "average_price": float(row.average_price), "listing_count": int(row.listing_count),
        }
        for row in grouped.sort_values("date").itertuples(index=False)
    ]


def merge_clean_trend(
    points: list[dict[str, object]], clean_points: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Attach clean-declared aggregates to their matching real listing dates."""
    clean_by_date = {item["date"]: item for item in clean_points}
    merged: list[dict[str, object]] = []
    for point in points:
        item = dict(point)
        clean = clean_by_date.get(point["date"])
        if clean:
            item.update({
                "clean_median_price": clean["median_price"],
                "clean_average_price": clean["average_price"],
                "clean_listing_count": clean["listing_count"],
            })
        merged.append(item)
    return merged


def unavailable_changes() -> dict[str, float | None]:
    return {"change_30d": None, "change_90d": None, "change_yoy": None}


def snapshot_changes(
    connection: sqlite3.Connection,
    dimension_type: str = "market",
    dimension_value: str = "all",
) -> dict[str, float | None]:
    """Calculate changes only from separately captured daily snapshots."""
    table_exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (SNAPSHOT_TABLE,)
    ).fetchone()
    empty = unavailable_changes()
    if not table_exists:
        return empty
    rows = connection.execute(
        f"""SELECT snapshot_date, median_price FROM {SNAPSHOT_TABLE}
            WHERE dimension_type=? AND dimension_value=? ORDER BY snapshot_date""",
        (dimension_type, dimension_value),
    ).fetchall()
    if len(rows) < 2:
        return empty
    latest_date = pd.Timestamp(rows[-1][0]).date()
    latest_price = float(rows[-1][1])
    values = [(pd.Timestamp(row[0]).date(), float(row[1])) for row in rows]

    def change(days: int) -> float | None:
        target = latest_date - timedelta(days=days)
        candidates = [(day, price) for day, price in values if day <= target]
        if not candidates:
            return None
        baseline = candidates[-1][1]
        return ((latest_price - baseline) / baseline * 100) if baseline else None

    return {"change_30d": change(30), "change_90d": change(90), "change_yoy": change(365)}
