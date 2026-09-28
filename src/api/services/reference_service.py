"""Look up the TSB kasko reference value for a vehicle.

The published list names vehicles by brand and a free-text "tip" such as
``EGEA 1.4 FIRE EASY``. A vehicle matches when the brand is the same and every
word of its series appears in the tip. When the package's words appear too, that
package's value is used; otherwise the answer is the median of the series for
that model year, and the response says which of the two it is.

This is an insurance reference value, never an asking price, and it is always
labelled as such.
"""

from __future__ import annotations

import re
import sqlite3
from statistics import median

from src.ingestion.tsb_reference import REFERENCE_TABLE, SOURCE_TSB, normalize_header

MATCH_MODEL = "model"
MATCH_SERIES = "series"


# Catalog series such as "3 Serisi" or "C Serisi" never spell that word in a tip.
GENERIC_SERIES_WORDS = {"serisi", "series", "class"}


def tokens(value: object) -> set[str]:
    return {token for token in re.split(r"[^a-z0-9.]+", normalize_header(value)) if token}


def _token_present(wanted: str, available: set[str]) -> bool:
    """A numeric series such as "3" also matches model codes like "320i" or "318d"."""
    if wanted in available:
        return True
    if not wanted.isdigit():
        return False
    return any(
        token.startswith(wanted) and token[len(wanted):len(wanted) + 1].isdigit()
        for token in available
    )


def _contains(wanted: set[str], name: str) -> bool:
    available = tokens(name)
    return all(_token_present(token, available) for token in wanted)


def _latest_period(connection: sqlite3.Connection) -> tuple[str, str] | None:
    """Prefer the official list; fall back to demo values only when it is absent."""
    rows = connection.execute(
        f"SELECT source, MAX(period) FROM {REFERENCE_TABLE} GROUP BY source"
    ).fetchall()
    periods = {str(source): str(period) for source, period in rows if period}
    if SOURCE_TSB in periods:
        return SOURCE_TSB, periods[SOURCE_TSB]
    if periods:
        source = sorted(periods)[0]
        return source, periods[source]
    return None


def lookup_reference_value(
    connection: sqlite3.Connection,
    brand: str | None,
    series: str | None,
    model: str | None,
    year: int | None,
) -> dict[str, object] | None:
    if not brand or not series or year is None:
        return None
    exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (REFERENCE_TABLE,)
    ).fetchone()
    if not exists:
        return None
    latest = _latest_period(connection)
    if latest is None:
        return None
    source, period = latest

    brand_tokens = tokens(brand)
    series_tokens = tokens(series) - GENERIC_SERIES_WORDS
    if not series_tokens:
        return None
    rows = connection.execute(
        f"SELECT brand, model_name, reference_value FROM {REFERENCE_TABLE} "
        "WHERE source = ? AND period = ? AND model_year = ?",
        (source, period, int(year)),
    ).fetchall()
    candidates = [
        (str(name), float(value))
        for row_brand, name, value in rows
        if tokens(row_brand) == brand_tokens and _contains(series_tokens, str(name))
    ]
    if not candidates:
        return None

    base = {"period": period, "source": source, "model_year": int(year)}
    model_tokens = tokens(model) - series_tokens if model else set()
    if model_tokens:
        exact = [(name, value) for name, value in candidates if _contains(model_tokens, name)]
        if exact:
            # The shortest tip is the plainest variant carrying all of the package's words.
            name, value = min(exact, key=lambda item: (len(tokens(item[0])), item[1]))
            return {**base, "value": value, "match": MATCH_MODEL, "matched_name": name, "candidate_count": len(exact)}

    return {
        **base,
        "value": float(median(value for _, value in candidates)),
        "match": MATCH_SERIES,
        "matched_name": None,
        "candidate_count": len(candidates),
    }
