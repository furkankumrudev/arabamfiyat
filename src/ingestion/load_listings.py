"""Load listings from a source into the local database and rebuild the analysis.

    python -m src.ingestion.load_listings demo
    python -m src.ingestion.load_listings csv data/import/ilanlar.csv --source-name partner

Synthetic demo rows and real rows are never mixed in one database: a demo
market trend computed over real listings, or the reverse, would be meaningless.
"""

from __future__ import annotations

import argparse
import logging
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd

from src.api.database import ListingRepository
from src.api.settings import sqlite_db_path
from src.ingestion.sources.base import ListingSource
from src.ingestion.sources.csv_file import CsvFormatError, CsvSource
from src.ingestion.sources.demo import DEMO_SOURCE, DemoConfig, DemoSource, demo_reference_values
from src.ingestion.storage import ListingStore
from src.ingestion.tsb_reference import REFERENCE_TABLE, ensure_reference_table
from src.maintenance.pipeline import run_pipeline
from src.maintenance.save_market_snapshot import save_snapshot_frame

logger = logging.getLogger(__name__)

# The demo spans several months, so it can carry the weekly history a real
# deployment would have accumulated; real data never gets backfilled.
# Fourteen weeks is enough history for the 30 and 90 day change columns.
DEMO_SNAPSHOT_WEEKS = 14


class MixedSourcesError(RuntimeError):
    """Demo and real listings would end up in the same database."""


@dataclass(frozen=True, slots=True)
class LoadResult:
    source: str
    read: int
    changed: int


def load_source(source: ListingSource, db_path: Path) -> LoadResult:
    """Upsert every listing from ``source`` into the raw listing table."""
    with ListingStore(db_path) as store:
        existing = store.sources()
        others = set(existing) - {source.name}
        if others and (source.name == DEMO_SOURCE or DEMO_SOURCE in others):
            raise MixedSourcesError(
                "Demo verisi gercek ilanlarla ayni veritabanina yuklenemez. "
                f"Mevcut kaynaklar: {', '.join(sorted(existing))}. Farkli bir --db-path kullanin "
                f"ya da {db_path} dosyasini silip yeniden yukleyin."
            )
        listings = list(source.listings())
        changed = store.upsert_many(listings)
    return LoadResult(source=source.name, read=len(listings), changed=changed)


def backfill_demo_snapshots(db_path: Path, reference_date: date, weeks: int = DEMO_SNAPSHOT_WEEKS) -> int:
    """Give the demo the weekly market history a running deployment would have."""
    repository = ListingRepository(db_path)
    listings = repository.load_listings()
    if listings.empty:
        return 0
    listings = listings.assign(parsed_date=pd.to_datetime(listings["parsed_listing_date"], errors="coerce"))
    listings = listings.dropna(subset=["parsed_date"])
    saved = 0
    with closing(repository.connect()) as connection:
        for week in range(weeks, 0, -1):
            day = reference_date - timedelta(weeks=week)
            # The daily snapshot summarises every stored listing, so each past
            # week summarises the listings that had been published by then.
            window = listings[listings["parsed_date"] <= pd.Timestamp(day)]
            saved += save_snapshot_frame(connection, window, day)
    return saved


def write_demo_reference_values(db_path: Path, reference_date: date) -> int:
    """Store the synthetic kasko list for the demo's month, labelled as demo."""
    period = reference_date.strftime("%Y-%m")
    loaded_at = datetime.now(UTC).isoformat()
    rows = [
        (DEMO_SOURCE, period, None, brand, tip, year, value, loaded_at)
        for brand, tip, year, value in demo_reference_values(reference_date)
    ]
    with closing(sqlite3.connect(db_path)) as connection:
        ensure_reference_table(connection)
        connection.execute(f"DELETE FROM {REFERENCE_TABLE} WHERE source = ?", (DEMO_SOURCE,))
        connection.executemany(
            f"""INSERT INTO {REFERENCE_TABLE}
                (source, period, vehicle_code, brand, model_name, model_year, reference_value, loaded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
        connection.commit()
    return len(rows)


def build_parser() -> argparse.ArgumentParser:
    # Shared options live on every subcommand so wrapper scripts can append them.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--db-path", type=Path, default=None)
    common.add_argument("--skip-pipeline", action="store_true", help="Yalnizca ham tabloya yaz.")

    parser = argparse.ArgumentParser(description="Ilan verisini yukle ve analiz tablolarini yeniden olustur.")
    commands = parser.add_subparsers(dest="command", required=True)

    demo = commands.add_parser("demo", parents=[common], help="Sentetik demo ilanlari uret.")
    demo.add_argument("--count", type=int, default=DemoConfig().count)
    demo.add_argument("--seed", type=int, default=DemoConfig().seed)
    demo.add_argument("--if-missing", action="store_true", help="Veritabani zaten varsa hicbir sey yapma.")

    csv_import = commands.add_parser("csv", parents=[common], help="CSV dosyasindan ilan aktar.")
    csv_import.add_argument("path", type=Path)
    csv_import.add_argument("--source-name", default=None, help="Varsayilan: dosya adi.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    db_path = args.db_path or sqlite_db_path()
    today = date.today()

    if args.command == "demo" and args.if_missing and db_path.exists():
        print(f"Veritabani mevcut, demo verisi yuklenmedi: {db_path}")
        return 0

    source: ListingSource
    if args.command == "demo":
        source = DemoSource(DemoConfig(count=args.count, seed=args.seed), reference_date=today)
    else:
        source = CsvSource(args.path, args.source_name)

    try:
        result = load_source(source, db_path)
    except (CsvFormatError, MixedSourcesError) as error:
        print(f"Yukleme yapilmadi: {error}")
        return 1
    print(f"source={result.source} read={result.read} changed={result.changed} db={db_path}")
    if isinstance(source, CsvSource) and source.skipped_columns:
        print(f"Taninmayan sutunlar yok sayildi: {', '.join(source.skipped_columns)}")

    if args.skip_pipeline:
        return 0
    steps = run_pipeline(db_path, snapshot_date=today)
    for step in steps:
        print(f"{step.step}={step.status} {step.detail}")
    if args.command == "demo":
        print(f"demo_snapshots={backfill_demo_snapshots(db_path, today)}")
        print(f"demo_reference_values={write_demo_reference_values(db_path, today)}")
    return 0 if all(step.succeeded for step in steps) else 1


if __name__ == "__main__":
    raise SystemExit(main())
