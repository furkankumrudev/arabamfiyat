"""Parse the listing-date formats the listing sources emit."""

from __future__ import annotations

import re
from datetime import date, timedelta

import pandas as pd

TURKISH_MONTHS = {
    "ocak": 1, "şubat": 2, "subat": 2, "mart": 3, "nisan": 4,
    "mayıs": 5, "mayis": 5, "haziran": 6, "temmuz": 7, "ağustos": 8,
    "agustos": 8, "eylül": 9, "eylul": 9, "ekim": 10, "kasım": 11,
    "kasim": 11, "aralık": 12, "aralik": 12,
}


def parse_listing_date(value: object) -> pd.Timestamp | None:
    """Parse one listing date without inventing dates."""
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


def parse_listing_dates(values: pd.Series) -> pd.Series:
    """Parse a whole column, once per distinct value.

    A listing table holds few distinct dates, so this is far faster than
    parsing every row, and gives exactly the same result.
    """
    parsed = {value: parse_listing_date(value) for value in values.dropna().unique()}
    return pd.to_datetime(values.map(parsed), errors="coerce")
