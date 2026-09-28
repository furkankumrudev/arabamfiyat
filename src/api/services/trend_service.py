"""Real listing-date aggregations and true snapshot-based change calculations."""

from __future__ import annotations

import re
import sqlite3
from datetime import date, timedelta

import pandas as pd

from ..database import SNAPSHOT_TABLE

TURKISH_MONTHS = {
    "ocak": 1, "şubat": 2, "subat": 2, "mart": 3, "nisan": 4,
    "mayıs": 5, "mayis": 5, "haziran": 6, "temmuz": 7, "ağustos": 8,
    "agustos": 8, "eylül": 9, "eylul": 9, "ekim": 10, "kasım": 11,
    "kasim": 11, "aralık": 12, "aralik": 12,
}


def parse_listing_date(value: object) -> pd.Timestamp | None:
    """Parse the formats emitted by the listing source without inventing dates."""
    text = str(value or "").strip()
    if not text:
        return None
    folded = text.casefold()
    if folded == "bugün" or folded == "bugun":
        return pd.Timestamp(date.today())
    if folded == "dün" or folded == "dun":
        return pd.Timestamp(date.today() - timedelta(days=1))
    match = re.search(r"(\d{1,2})\s+([A-Za-zÇĞİÖŞÜçğıöşü]+)\s+(\d{4})", text)
    if match:
        month = TURKISH_MONTHS.get(match.group(2).casefold())
        if month:
            try:
                return pd.Timestamp(date(int(match.group(3)), month, int(match.group(1))))
            except ValueError:
                return None
    parsed = pd.to_datetime(text, errors="coerce", dayfirst=True)
    return None if pd.isna(parsed) else pd.Timestamp(parsed).normalize()


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
    frame = listings.copy()
    frame["date"] = frame["listing_date"].map(parse_listing_date)
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
