"""Small SQLite repository shared by the API and maintenance commands."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path
from threading import RLock
from typing import Any

import pandas as pd

from .listing_dates import parse_listing_dates
from .settings import sqlite_db_path

DEFAULT_DB_PATH = sqlite_db_path()

LISTING_TABLES = ("vehicle_listings_clean", "vehicle_listings")
SNAPSHOT_TABLE = "market_price_snapshots"
LISTING_COLUMNS = (
    "id", "title", "brand", "series", "model", "year", "mileage_km",
    "transmission", "fuel_type", "body_type", "city", "district", "price",
    "currency", "listing_date", "listing_url", "image_url", "is_clean_claimed", "scraped_at",
)
# Matched case-insensitively against the values the dropdowns offer.
EXACT_FILTER_COLUMNS = ("brand", "series", "model", "body_type", "fuel_type", "transmission")


class DatabaseUnavailable(RuntimeError):
    """Raised when the local listing database cannot be used."""


class ListingRepository:
    """Parameterized, read-focused access to the local listing database."""

    def __init__(self, db_path: Path = DEFAULT_DB_PATH) -> None:
        self.db_path = db_path
        self._cache: tuple[tuple[int, date], pd.DataFrame] | None = None
        self._folded_cache: dict[tuple[int, str], pd.Series] = {}
        self._cache_lock = RLock()

    def connect(self) -> sqlite3.Connection:
        if not self.db_path.exists():
            raise DatabaseUnavailable("Veritabanı henüz bulunamadı.")
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def listing_table(self, connection: sqlite3.Connection | None = None) -> str:
        owns_connection = connection is None
        connection = connection or self.connect()
        try:
            rows = connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
            tables = {str(row[0]) for row in rows}
            empty_table: str | None = None
            for table in LISTING_TABLES:
                if table in tables:
                    has_rows = connection.execute(
                        f"SELECT 1 FROM {table} LIMIT 1"
                    ).fetchone()
                    if has_rows is not None:
                        return table
                    empty_table = empty_table or table

            # A cleaning run rebuilds the derived table from scratch. If it is
            # interrupted, keep the application usable with the raw records.
            if empty_table:
                return empty_table
        finally:
            if owns_connection:
                connection.close()
        raise DatabaseUnavailable("İlan tablosu henüz oluşturulmadı.")

    def table_columns(self, table: str) -> set[str]:
        if table not in (*LISTING_TABLES, SNAPSHOT_TABLE):
            raise ValueError("Geçersiz tablo adı.")
        with closing(self.connect()) as connection:
            return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}

    def listing_count(self) -> int:
        with closing(self.connect()) as connection:
            table = self.listing_table(connection)
            return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])

    def load_listings(self, filters: dict[str, Any] | None = None) -> pd.DataFrame:
        """Return real listings matching ``filters``; user values never reach SQL text.

        The whole table is read once per database version and filtered in
        memory. Reading it again for every filter combination made each page
        load re-read hundreds of thousands of rows several times.
        """
        frame = self._all_listings()
        active = {key: value for key, value in (filters or {}).items() if value is not None and value != "" and value is not False}
        if not active:
            # Copy-on-write: no data is copied unless the caller changes it.
            return frame.copy(deep=False)
        filters = active
        mask = pd.Series(True, index=frame.index)
        for column in EXACT_FILTER_COLUMNS:
            value = filters.get(column)
            if value and column in frame:
                mask &= self._folded(frame, column) == str(value).strip().casefold()
        if filters.get("clean_only") and "is_clean_claimed" in frame:
            mask &= pd.to_numeric(frame["is_clean_claimed"], errors="coerce").fillna(0).astype(int) == 1
        if filters.get("year_min") is not None and "year" in frame:
            mask &= frame["year"] >= int(filters["year_min"])
        if filters.get("year_max") is not None and "year" in frame:
            mask &= frame["year"] <= int(filters["year_max"])
        if filters.get("mileage_max") is not None and "mileage_km" in frame:
            mask &= frame["mileage_km"] <= int(filters["mileage_max"])
        # Copy-on-write makes this cheap; callers may add columns freely.
        return frame[mask].copy()

    def warm(self) -> None:
        """Load the listing table into the cache ahead of the first request."""
        self._all_listings()

    def _all_listings(self) -> pd.DataFrame:
        try:
            mtime = self.db_path.stat().st_mtime_ns
        except FileNotFoundError as exc:
            raise DatabaseUnavailable("Veritabanı henüz bulunamadı.") from exc
        # "Bugün" and "Dün" listing dates depend on the day they are read.
        version = (mtime, date.today())
        with self._cache_lock:
            if self._cache is not None and self._cache[0] == version:
                return self._cache[1]
            with closing(self.connect()) as connection:
                table = self.listing_table(connection)
                columns = {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}
                selected = [column for column in LISTING_COLUMNS if column in columns]
                if "price" not in selected:
                    raise DatabaseUnavailable("İlan tablosunda fiyat alanı bulunamadı.")
                # Plain tuples and a direct fetch are several times faster than
                # sqlite3.Row objects or read_sql_query on large tables.
                connection.row_factory = None
                cursor = connection.execute(
                    f"SELECT {', '.join(selected)} FROM {table} WHERE price IS NOT NULL AND price > 0"
                )
                frame = pd.DataFrame.from_records(cursor.fetchall(), columns=selected)
            for column in ("price", "year", "mileage_km"):
                if column in frame:
                    frame[column] = pd.to_numeric(frame[column], errors="coerce")
            frame = frame.dropna(subset=["price"]).reset_index(drop=True)
            if "listing_date" in frame:
                frame["parsed_listing_date"] = parse_listing_dates(frame["listing_date"])
            self._cache = (version, frame)
            self._folded_cache = {}
            return frame

    def _folded(self, frame: pd.DataFrame, column: str) -> pd.Series:
        """Case-folded text of a column, computed once per database version."""
        # Keyed by the frame itself so a reload running in parallel never mixes versions.
        key = (id(frame), column)
        folded = self._folded_cache.get(key)
        if folded is None:
            folded = frame[column].fillna("").astype(str).str.strip().str.casefold()
            self._folded_cache[key] = folded
        return folded

    def distinct_values(self, column: str, filters: dict[str, Any] | None = None) -> list[str]:
        if column not in {"brand", "series", "model", "body_type", "fuel_type", "transmission"}:
            raise ValueError("Geçersiz filtre alanı.")
        frame = self.load_listings(filters)
        if column not in frame:
            return []
        values = frame[column].dropna().astype(str).str.strip()
        return sorted(value for value in values.unique().tolist() if value)

    def last_updated_at(self) -> str | None:
        with closing(self.connect()) as connection:
            table = self.listing_table(connection)
            columns = {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}
            if "scraped_at" not in columns:
                return None
            value = connection.execute(
                f"SELECT MAX(scraped_at) FROM {table} WHERE scraped_at IS NOT NULL"
            ).fetchone()[0]
            return str(value) if value else None


def ensure_snapshot_table(connection: sqlite3.Connection) -> None:
    """Create the forward-looking market snapshot store without backfilling data."""
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {SNAPSHOT_TABLE} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_date TEXT NOT NULL,
            dimension_type TEXT NOT NULL,
            dimension_value TEXT NOT NULL,
            dimension_key TEXT NOT NULL,
            brand TEXT,
            series TEXT,
            model TEXT,
            body_type TEXT,
            average_price REAL NOT NULL,
            median_price REAL NOT NULL,
            q1_price REAL,
            q3_price REAL,
            listing_count INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(snapshot_date, dimension_type, dimension_key)
        )
        """
    )
    columns = {str(row[1]) for row in connection.execute(f"PRAGMA table_info({SNAPSHOT_TABLE})")}
    if "dimension_key" not in columns:
        connection.execute(f"ALTER TABLE {SNAPSHOT_TABLE} ADD COLUMN dimension_key TEXT NOT NULL DEFAULT ''")
        connection.execute(
            f"UPDATE {SNAPSHOT_TABLE} SET dimension_key = dimension_type || ':' || LOWER(TRIM(dimension_value)) "
            "WHERE dimension_key = ''"
        )
    connection.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{SNAPSHOT_TABLE}_dimension_date "
        f"ON {SNAPSHOT_TABLE}(dimension_type, dimension_value, snapshot_date)"
    )
    connection.execute(
        f"CREATE UNIQUE INDEX IF NOT EXISTS idx_{SNAPSHOT_TABLE}_identity "
        f"ON {SNAPSHOT_TABLE}(snapshot_date, dimension_type, dimension_key)"
    )
    connection.commit()
