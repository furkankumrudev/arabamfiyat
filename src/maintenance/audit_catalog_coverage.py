"""Compare the selector catalogue with locally stored listing coverage."""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from src.data_paths import DEFAULT_DB_PATH
from src.maintenance.clean_vehicle_data import (
    CATALOG_PATH,
    CLEAN_TABLE,
    RAW_TABLE,
    CleanRules,
    duplicate_keys,
    load_catalog_brands,
    normalize_key,
    normalize_row,
    reject_reason,
    table_columns,
)

DEFAULT_OUTPUT_DIR = Path("data") / "runtime" / "coverage_reports"


@dataclass(frozen=True, slots=True)
class CatalogSeries:
    brand: str
    series: str
    models: tuple[str, ...]


def canonical_series_name(value: object, brand: str) -> str:
    text = str(value or "").strip()
    if normalize_key(brand) == "mercedesbenz" and len(text) == 1 and text.isalpha():
        return f"{text.upper()} Serisi"
    return text


def canonical_catalog_series() -> list[CatalogSeries]:
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    brand_map = load_catalog_brands(CATALOG_PATH)
    entries: list[CatalogSeries] = []
    for brand_entry in catalog.get("brands", []):
        raw_brand = str(brand_entry.get("name", "")).strip()
        brand = brand_map.get(normalize_key(raw_brand), raw_brand)
        if not brand:
            continue
        for series_entry in brand_entry.get("series", []):
            series = canonical_series_name(series_entry.get("name", ""), brand)
            if not series:
                continue
            models = tuple(
                str(model).strip()
                for model in series_entry.get("models", [])
                if str(model).strip()
            )
            entries.append(CatalogSeries(brand=brand, series=series, models=models))
    return entries


def clean_table_has_rows(connection: sqlite3.Connection) -> bool:
    tables = {
        str(row[0])
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    if CLEAN_TABLE not in tables:
        return False
    return bool(connection.execute(f"SELECT 1 FROM {CLEAN_TABLE} LIMIT 1").fetchone())


def aggregate_rows(rows: Iterable[tuple[object, object, object, int]]) -> tuple[Counter[str], Counter[tuple[str, str]], Counter[tuple[str, str, str]]]:
    brand_counts: Counter[str] = Counter()
    series_counts: Counter[tuple[str, str]] = Counter()
    model_counts: Counter[tuple[str, str, str]] = Counter()
    for brand, series, model, count in rows:
        quantity = int(count)
        brand_key = normalize_key(brand)
        series_key = normalize_key(series)
        model_key = normalize_key(model)
        if brand_key:
            brand_counts[brand_key] += quantity
        if brand_key and series_key:
            series_counts[(brand_key, series_key)] += quantity
        if brand_key and series_key and model_key:
            model_counts[(brand_key, series_key, model_key)] += quantity
    return brand_counts, series_counts, model_counts


def aggregate_clean_table(connection: sqlite3.Connection) -> tuple[Counter[str], Counter[tuple[str, str]], Counter[tuple[str, str, str]]]:
    rows = connection.execute(
        f"""
        SELECT brand, series, model, COUNT(*)
        FROM {CLEAN_TABLE}
        GROUP BY brand, series, model
        """
    )
    return aggregate_rows(rows)


def aggregate_normalized_raw(connection: sqlite3.Connection) -> tuple[Counter[str], Counter[tuple[str, str]], Counter[tuple[str, str, str]]]:
    """Mirror the cleaning rules in memory while a clean-table rebuild is underway."""
    brand_map = load_catalog_brands(CATALOG_PATH)
    known_brand_keys = {normalize_key(value) for value in brand_map.values()}
    rules = CleanRules(
        min_price=50_000,
        max_price=150_000_000,
        min_year=1980,
        max_year=2026,
        max_mileage=700_000,
    )
    seen_keys: set[tuple[str, ...]] = set()
    counts: Counter[tuple[str, str, str]] = Counter()
    connection.row_factory = sqlite3.Row
    raw_columns = table_columns(connection, RAW_TABLE)
    order_by = "datetime(scraped_at) DESC, id DESC" if "id" in raw_columns else "datetime(scraped_at) DESC"
    for sqlite_row in connection.execute(f"SELECT * FROM {RAW_TABLE} ORDER BY {order_by}"):
        row, *_ = normalize_row(dict(sqlite_row), brand_map)
        if reject_reason(row, rules, known_brand_keys, seen_keys):
            continue
        seen_keys.update(duplicate_keys(row))
        counts[(row.get("brand"), row.get("series"), row.get("model"))] += 1

    rows = ((brand, series, model, count) for (brand, series, model), count in counts.items())
    return aggregate_rows(rows)


def status(count: int, threshold: int) -> str:
    if count == 0:
        return "missing"
    if count <= threshold:
        return "low"
    return "covered"


def write_csv(path: Path, headers: list[str], rows: Iterable[tuple[object, ...]]) -> Path:
    def write(target: Path) -> None:
        with target.open("w", encoding="utf-8-sig", newline="") as output:
            writer = csv.writer(output)
            writer.writerow(headers)
            writer.writerows(rows)

    try:
        write(path)
        return path
    except PermissionError:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        fallback = path.with_name(f"{path.stem}_{timestamp}{path.suffix}")
        write(fallback)
        return fallback


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit selector catalogue coverage in the local listing database.")
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--series-low-threshold", type=int, default=7)
    parser.add_argument("--model-low-threshold", type=int, default=2)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--limit", type=int, default=30, help="Maximum gap rows to print per section.")
    parser.add_argument("--no-files", action="store_true", help="Print only; do not write CSV reports.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.series_low_threshold < 0 or args.model_low_threshold < 0:
        raise SystemExit("Coverage thresholds must be zero or greater.")

    catalog_entries = canonical_catalog_series()
    path = Path(args.db_path)
    with sqlite3.connect(path) as connection:
        if clean_table_has_rows(connection):
            source = CLEAN_TABLE
            brand_counts, series_counts, model_counts = aggregate_clean_table(connection)
        else:
            source = f"{RAW_TABLE} (normalized in memory while clean rebuild is in progress)"
            brand_counts, series_counts, model_counts = aggregate_normalized_raw(connection)

    catalog_brands = sorted({item.brand for item in catalog_entries})
    brand_rows = [
        (brand, brand_counts[normalize_key(brand)], status(brand_counts[normalize_key(brand)], args.series_low_threshold))
        for brand in catalog_brands
    ]
    series_rows = [
        (
            item.brand,
            item.series,
            series_counts[(normalize_key(item.brand), normalize_key(item.series))],
        )
        for item in catalog_entries
    ]
    model_rows = [
        (
            item.brand,
            item.series,
            model,
            model_counts[(normalize_key(item.brand), normalize_key(item.series), normalize_key(model))],
        )
        for item in catalog_entries
        for model in item.models
    ]

    missing_brands = [row for row in brand_rows if row[1] == 0]
    missing_series = [row for row in series_rows if row[2] == 0]
    low_series = [row for row in series_rows if 0 < row[2] <= args.series_low_threshold]
    missing_models = [row for row in model_rows if row[3] == 0]
    low_models = [row for row in model_rows if 0 < row[3] <= args.model_low_threshold]

    print(f"source={source}")
    print(
        f"catalog_brands={len(catalog_brands)} catalog_series={len(series_rows)} "
        f"catalog_packages={len(model_rows)}"
    )
    print(
        f"missing_brands={len(missing_brands)} missing_series={len(missing_series)} "
        f"low_series_1_to_{args.series_low_threshold}={len(low_series)}"
    )
    print(
        f"missing_packages={len(missing_models)} low_packages_1_to_{args.model_low_threshold}={len(low_models)}"
    )

    def print_rows(label: str, rows: list[tuple[object, ...]]) -> None:
        print(label)
        for row in rows[: args.limit]:
            print("  " + " / ".join(str(value) for value in row))
        if len(rows) > args.limit:
            print(f"  ... {len(rows) - args.limit} more")

    print_rows("MISSING_BRANDS", missing_brands)
    print_rows("MISSING_SERIES", missing_series)
    print_rows("LOW_SERIES", low_series)

    if not args.no_files:
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        report_paths = []
        report_paths.append(write_csv(output_dir / "brand_coverage.csv", ["brand", "listing_count", "status"], brand_rows))
        report_paths.append(write_csv(
            output_dir / "series_coverage.csv",
            ["brand", "series", "listing_count", "status"],
            [(*row, status(row[2], args.series_low_threshold)) for row in series_rows],
        ))
        report_paths.append(write_csv(
            output_dir / "package_coverage.csv",
            ["brand", "series", "package", "listing_count", "status"],
            [(*row, status(row[3], args.model_low_threshold)) for row in model_rows],
        ))
        print("reports=" + ", ".join(str(path) for path in report_paths))


if __name__ == "__main__":
    main()
