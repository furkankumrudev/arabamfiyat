"""SQLite storage adapter for vehicle listings from any source."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from pathlib import Path

from src.data_paths import DEFAULT_DB_PATH

from .schema import VehicleListing


class ListingStore:
    """Persist normalized vehicle listings in SQLite.

    SQLite is the default local development store. The schema is intentionally
    close to the ML feature set so that PostgreSQL can be added later without
    changing the scraper interface.
    """

    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.db_path)
        self.connection.row_factory = sqlite3.Row
        self.create_tables()

    def create_tables(self) -> None:
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS vehicle_listings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                source_listing_id TEXT,
                title TEXT NOT NULL,
                brand TEXT,
                series TEXT,
                model TEXT,
                year INTEGER,
                mileage_km INTEGER,
                transmission TEXT,
                fuel_type TEXT,
                body_type TEXT,
                color TEXT,
                engine TEXT,
                city TEXT,
                district TEXT,
                seller_type TEXT,
                price INTEGER,
                currency TEXT NOT NULL DEFAULT 'TRY',
                listing_date TEXT,
                listing_url TEXT,
                image_url TEXT,
                paint_status TEXT,
                changed_part_status TEXT,
                damage_status TEXT,
                is_clean_claimed INTEGER NOT NULL DEFAULT 0,
                scrape_segment TEXT,
                scraped_at TEXT NOT NULL,
                UNIQUE(source, source_listing_id)
            )
            """
        )
        for column in [
            "paint_status TEXT",
            "changed_part_status TEXT",
            "damage_status TEXT",
            "is_clean_claimed INTEGER NOT NULL DEFAULT 0",
            "scrape_segment TEXT",
        ]:
            column_name = column.split()[0]
            existing = {
                str(row["name"])
                for row in self.connection.execute("PRAGMA table_info(vehicle_listings)").fetchall()
            }
            if column_name not in existing:
                self.connection.execute(f"ALTER TABLE vehicle_listings ADD COLUMN {column}")
        self.connection.commit()

    def upsert_listing(self, listing: VehicleListing, commit: bool = True) -> bool:
        data = listing.to_dict()
        columns = list(data)
        placeholders = ", ".join([":" + column for column in columns])
        update_columns = [column for column in columns if column not in {"source", "source_listing_id"}]
        preserve_columns = {"paint_status", "changed_part_status", "damage_status"}
        update_sql = ", ".join(
            [
                f"{column}=COALESCE(excluded.{column}, {column})"
                if column in preserve_columns
                else f"{column}=MAX(COALESCE(excluded.{column}, 0), COALESCE({column}, 0))"
                if column == "is_clean_claimed"
                else f"{column}=excluded.{column}"
                for column in update_columns
            ]
        )

        before = self.connection.total_changes
        self.connection.execute(
            f"""
            INSERT INTO vehicle_listings ({", ".join(columns)})
            VALUES ({placeholders})
            ON CONFLICT(source, source_listing_id)
            DO UPDATE SET {update_sql}
            """,
            data,
        )
        if commit:
            self.connection.commit()
        return self.connection.total_changes > before

    def upsert_many(self, listings: Iterable[VehicleListing]) -> int:
        # One transaction for the batch: committing per row makes large imports crawl.
        changed = 0
        try:
            for listing in listings:
                if self.upsert_listing(listing, commit=False):
                    changed += 1
        except BaseException:
            self.connection.rollback()
            raise
        self.connection.commit()
        return changed

    def sources(self) -> dict[str, int]:
        rows = self.connection.execute("SELECT source, COUNT(*) FROM vehicle_listings GROUP BY source").fetchall()
        return {str(row[0]): int(row[1]) for row in rows}

    def count(self) -> int:
        row = self.connection.execute("SELECT COUNT(*) AS total FROM vehicle_listings").fetchone()
        return int(row["total"])

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> ListingStore:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
