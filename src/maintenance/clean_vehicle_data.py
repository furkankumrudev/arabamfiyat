"""Build cleaned vehicle listing tables from raw local source data.

This module keeps the raw scraper table untouched and creates three derived
tables:

- vehicle_listings_clean: normalized records used by the app/model
- vehicle_listings_rejected: records removed from the clean set with a reason
- vehicle_cleaning_report: small key/value quality report for quick inspection
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from src.data_paths import DEFAULT_DB_PATH
from src.maintenance.turkish_locations import TURKISH_PROVINCES

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = PROJECT_ROOT / "data" / "reference" / "vehicle_catalog.json"

RAW_TABLE = "vehicle_listings"
CLEAN_TABLE = "vehicle_listings_clean"
REJECTED_TABLE = "vehicle_listings_rejected"
REPORT_TABLE = "vehicle_cleaning_report"

TEXT_FIXES = {
    "Tofas": "Tofaş",
    "Tofaş": "Tofaş",
    "TofaÅŸ": "Tofaş",
    "TofaÅ£": "Tofaş",
    "Tofaţ": "Tofaş",
    "Sahin": "Şahin",
    "Şahin": "Şahin",
    "Ţahin": "Şahin",
    "Doğan": "Doğan",
    "Dogan": "Doğan",
    "Dođan": "Doğan",
    "Serçe": "Serçe",
    "Serce": "Serçe",
    "Ser?e": "Serçe",
    "Mercedes - Benz": "Mercedes-Benz",
    "Mercedes Benz": "Mercedes-Benz",
    "Mercedes-Benz": "Mercedes-Benz",
}

TOFAS_SERIES_BY_KEY = {
    "sahin": "Şahin",
    "ahin": "Şahin",
    "dogan": "Doğan",
    "kartal": "Kartal",
    "murat": "Murat",
    "serce": "Serçe",
}

TRANSMISSION_MAP = {
    "manuel": "Manuel",
    "duz": "Manuel",
    "düz": "Manuel",
    "otomatik": "Otomatik",
    "yarı otomatik": "Yarı Otomatik",
    "yari otomatik": "Yarı Otomatik",
}

FUEL_MAP = {
    "benzin": "Benzin",
    "dizel": "Dizel",
    "diesel": "Dizel",
    "lpg": "LPG",
    "benzin lpg": "Benzin & LPG",
    "benzin & lpg": "Benzin & LPG",
    "hibrit": "Hibrit",
    "hybrid": "Hibrit",
    "elektrik": "Elektrik",
    "elektrikli": "Elektrik",
}

BODY_MAP = {
    "sedan": "Sedan",
    "hatchback": "Hatchback",
    "station wagon": "Station Wagon",
    "suv": "SUV",
    "coupe": "Coupe",
    "cabrio": "Cabrio",
    "convertible": "Cabrio",
    "pick-up": "Pick-up",
    "pickup": "Pick-up",
}

SELLER_MAP = {
    "sahibinden": "Sahibinden",
    "galeriden": "Galeriden",
    "yetkili bayiden": "Yetkili Bayiden",
}

ACRONYM_FIXES = [
    "ABS",
    "AMG",
    "CDI",
    "CNG",
    "DCI",
    "DSG",
    "GTI",
    "LPG",
    "TSI",
    "TDI",
    "VTEC",
]


@dataclass(frozen=True, slots=True)
class ModelOutlierPolicy:
    """Conservative thresholds for rejecting placeholder-like asking prices."""

    min_group_size: int = 50
    median_multiplier: float = 20.0
    iqr_multiplier: float = 3.0

    def upper_price_bound(self, sorted_prices: list[int]) -> float:
        median = interpolated_quantile(sorted_prices, 0.50)
        q1 = interpolated_quantile(sorted_prices, 0.25)
        q3 = interpolated_quantile(sorted_prices, 0.75)
        return max(q3 + self.iqr_multiplier * (q3 - q1), median * self.median_multiplier)


DEFAULT_MIN_PRICE = 50_000
DEFAULT_MAX_PRICE = 150_000_000
DEFAULT_MIN_YEAR = 1980
DEFAULT_MAX_MILEAGE = 700_000


def default_max_year() -> int:
    """Upper model-year bound, derived rather than hardcoded.

    Dealers list next year's model year before the calendar turns, and a fixed
    bound would silently reject every new listing once the year rolls over.
    """
    return date.today().year + 1


@dataclass(frozen=True, slots=True)
class CleanRules:
    min_price: int = DEFAULT_MIN_PRICE
    max_price: int = DEFAULT_MAX_PRICE
    min_year: int = DEFAULT_MIN_YEAR
    max_year: int = field(default_factory=default_max_year)
    max_mileage: int = DEFAULT_MAX_MILEAGE
    model_outlier_policy: ModelOutlierPolicy = field(default_factory=ModelOutlierPolicy)


@dataclass(frozen=True, slots=True)
class CleanResult:
    raw_total: int
    clean_total: int
    rejected_total: int
    duplicate_total: int
    normalized_field_total: int
    corrected_brand_total: int
    corrected_location_total: int
    corrected_brand_page_field_total: int
    canonicalized_series_variant_total: int
    canonicalized_model_variant_total: int


def normalize_key(value: object) -> str:
    text = str(value or "").strip().casefold()
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "", text)


PROVINCE_BY_KEY = {normalize_key(name): name for name in TURKISH_PROVINCES}
PROVINCE_ALIASES = {
    "afyon": "Afyonkarahisar",
    "icel": "Mersin",
    "maras": "Kahramanmaraş",
}


def split_province_prefix(value: object) -> tuple[str | None, str | None]:
    """Return a canonical province and any district accidentally appended to it."""
    text = clean_text(value)
    if not text:
        return None, None

    parts = [part for part in re.split(r"[\s,/]+", text) if part]
    if not parts:
        return None, None

    province = PROVINCE_BY_KEY.get(normalize_key(parts[0])) or PROVINCE_ALIASES.get(normalize_key(parts[0]))
    if not province:
        return None, text
    district = " ".join(parts[1:]).strip() or None
    return province, district


def normalize_location(city: object, district: object) -> tuple[str | None, str | None]:
    """Canonicalize province names and move a city suffix into the district column."""
    city_text = clean_text(city)
    district_text = clean_text(district)
    canonical_city, city_suffix = split_province_prefix(city_text)
    district_city, district_suffix = split_province_prefix(district_text)

    normalized_city = canonical_city or city_text
    if city_suffix:
        normalized_district = city_suffix
    elif district_suffix and (canonical_city is None or district_city == canonical_city):
        normalized_district = district_suffix
    else:
        normalized_district = district_text

    if normalized_city and normalized_district and normalize_key(normalized_city) == normalize_key(normalized_district):
        normalized_district = None
    return normalized_city, normalized_district


def slugify(value: object) -> str:
    text = str(value or "").strip().casefold()
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = text.replace("&", " ")
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def clean_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    text = text.replace("\u00a0", " ").replace("\u00ad", "")
    text = text.replace("\u200b", "").replace("\ufeff", "")
    text = text.replace("–", "-").replace("—", "-")
    text = re.sub(r"\s+", " ", text).strip()
    if not text or text.casefold() in {"none", "null", "nan", "-", "--"}:
        return None
    return TEXT_FIXES.get(text, text)


def normalize_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value == value else None

    text = str(value).strip()
    if not text:
        return None
    digits = re.sub(r"[^0-9]", "", text)
    if not digits:
        return None
    return int(digits)


def normalize_currency(value: object) -> str:
    text = clean_text(value)
    if not text:
        return "TRY"
    key = normalize_key(text)
    if key in {"tl", "try", "turklirasi", "t"}:
        return "TRY"
    return text.upper()


def normalize_choice(value: object, mapping: dict[str, str]) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    key = normalize_key(text)
    return mapping.get(key, text)


def normalize_bool_int(value: object) -> int:
    if value is None:
        return 0
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, (int, float)):
        return 1 if int(value) == 1 else 0
    key = normalize_key(value)
    return 1 if key in {"1", "true", "yes", "evet"} else 0


def infer_clean_claim_from_title(title: object) -> tuple[str | None, str | None, str | None]:
    key = normalize_key(title)
    has_boyasiz = "boyasiz" in key
    has_degisensiz = "degisensiz" in key
    has_tramersiz = "tramersiz" in key
    if has_boyasiz:
        return (
            "Boyasız",
            "Değişensiz" if has_degisensiz else None,
            "clean_claimed_from_title",
        )
    if has_degisensiz and has_tramersiz:
        return None, "Değişensiz", "clean_claimed_from_title"
    return None, "Değişensiz" if has_degisensiz else None, None


def normalize_color(value: object) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    return TEXT_FIXES.get(text, text[:1].upper() + text[1:].lower())


def normalize_package(value: object) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    text = re.sub(r"\s*/\s*", " / ", text)
    text = re.sub(r"\s+", " ", text).strip()
    for acronym in ACRONYM_FIXES:
        text = re.sub(rf"\b{re.escape(acronym)}\b", acronym, text, flags=re.IGNORECASE)
    text = re.sub(r"\bblue\s*motion\b", "BlueMotion", text, flags=re.IGNORECASE)
    text = re.sub(r"\bblue\s*hdi\b", "BlueHDi", text, flags=re.IGNORECASE)
    text = re.sub(r"\bblue\s*tec\b", "BlueTEC", text, flags=re.IGNORECASE)
    text = re.sub(r"\bmultijet\b", "Multijet", text, flags=re.IGNORECASE)
    text = re.sub(r"\becoboost\b", "EcoBoost", text, flags=re.IGNORECASE)
    return text


def load_catalog_brands(path: Path) -> dict[str, str]:
    catalog = json.loads(path.read_text(encoding="utf-8"))
    brands: dict[str, str] = {}
    for item in catalog.get("brands", []):
        if not isinstance(item, dict) or not item.get("name"):
            continue
        name = clean_text(item["name"])
        if not name:
            continue
        canonical = TEXT_FIXES.get(name, name)
        brands[normalize_key(canonical)] = canonical
        brands[slugify(canonical)] = canonical

    # Real market brands that can appear in scraped data but may be absent from
    # the static catalog or written differently on listing pages.
    extra_brands = [
        "TOGG",
        "Tesla",
        "Ferrari",
        "Lamborghini",
        "Bentley",
        "Rolls-Royce",
        "Maserati",
        "Porsche",
    ]
    for name in extra_brands:
        brands[normalize_key(name)] = name
        brands[slugify(name)] = name

    brands["tofas"] = "Tofaş"
    brands["tofa"] = "Tofaş"
    brands["tofat"] = "Tofaş"
    brands["mercedesbenz"] = "Mercedes-Benz"
    brands["mercedes-benz"] = "Mercedes-Benz"
    return brands


def infer_brand_from_url(listing_url: object, brand_by_slug: dict[str, str]) -> str | None:
    url = clean_text(listing_url)
    if not url:
        return None
    match = re.search(r"/ilan/vasita-otomobil-([^/]+?)/detay", url)
    if not match:
        match = re.search(r"/ilan/vasita-otomobil-([^/]+)", url)
    if not match:
        return None
    listing_slug = match.group(1).casefold()
    for slug in sorted(brand_by_slug, key=len, reverse=True):
        if listing_slug == slug or listing_slug.startswith(f"{slug}-"):
            return brand_by_slug[slug]
    return None


def canonical_brand(raw_brand: object, listing_url: object, brand_map: dict[str, str]) -> tuple[str | None, bool]:
    fixed_raw = clean_text(raw_brand)
    if fixed_raw:
        fixed_raw = TEXT_FIXES.get(fixed_raw, fixed_raw)

    by_key = brand_map.get(normalize_key(fixed_raw)) or brand_map.get(slugify(fixed_raw))
    by_url = infer_brand_from_url(listing_url, brand_map)

    if by_url and by_key != by_url:
        return by_url, True
    if by_key:
        return by_key, by_key != fixed_raw
    if by_url:
        return by_url, True
    return fixed_raw, fixed_raw != raw_brand


def normalize_series(value: object, brand: str | None) -> str | None:
    text = normalize_package(value)
    if not text:
        return None

    if normalize_key(brand) == "mercedesbenz" and len(text) == 1 and text.isalpha():
        return f"{text.upper()} Serisi"
    return text


def cosmetic_variant_key(value: object) -> str:
    """Compare names while preserving meaningful package markers such as '+'."""
    text = clean_text(value) or ""
    return re.sub(r"[\s-]+", "", text).casefold()


def infer_tofas_series(*values: object) -> str | None:
    haystack = " ".join(clean_text(value) or "" for value in values)
    haystack_key = normalize_key(haystack)
    for key, series in TOFAS_SERIES_BY_KEY.items():
        if key and key in haystack_key:
            return series
    return None


def normalize_tofas_series(series: object, *signals: object) -> str | None:
    series_key = normalize_key(series)
    if series_key in TOFAS_SERIES_BY_KEY:
        return TOFAS_SERIES_BY_KEY[series_key]
    return infer_tofas_series(*signals) or clean_text(series)


def normalize_row(row: dict[str, Any], brand_map: dict[str, str]) -> tuple[dict[str, Any], int, bool, bool, bool]:
    normalized = dict(row)
    changed_fields = 0

    def set_field(column: str, value: Any) -> None:
        nonlocal changed_fields
        if normalized.get(column) != value:
            changed_fields += 1
        normalized[column] = value

    raw_brand = clean_text(normalized.get("brand"))
    raw_series = clean_text(normalized.get("series"))
    raw_model = clean_text(normalized.get("model"))
    raw_engine = clean_text(normalized.get("engine"))
    url_brand = infer_brand_from_url(normalized.get("listing_url"), brand_map)
    raw_brand_is_known = bool(
        raw_brand
        and (brand_map.get(normalize_key(raw_brand)) or brand_map.get(slugify(raw_brand)))
    )
    brand_page_fields_shifted = bool(
        url_brand
        and raw_brand
        and normalize_key(raw_brand) != normalize_key(url_brand)
        and not raw_brand_is_known
    )

    brand, brand_changed = canonical_brand(raw_brand, normalized.get("listing_url"), brand_map)
    set_field("brand", brand)
    set_field("title", clean_text(normalized.get("title")) or "")
    if brand_page_fields_shifted:
        set_field("series", normalize_series(raw_brand, brand))
        set_field("model", normalize_package(raw_series))
        set_field("engine", raw_model or raw_engine)
    else:
        set_field("series", normalize_series(raw_series, brand))
        set_field("model", normalize_package(raw_model))
    if normalize_key(brand) == "tofas":
        set_field("series", normalize_tofas_series(normalized.get("series"), normalized.get("title"), raw_series, raw_model))
    set_field("year", normalize_int(normalized.get("year")))
    set_field("mileage_km", normalize_int(normalized.get("mileage_km")))
    set_field("price", normalize_int(normalized.get("price")))
    set_field("currency", normalize_currency(normalized.get("currency")))
    set_field("transmission", normalize_choice(normalized.get("transmission"), TRANSMISSION_MAP))
    set_field("fuel_type", normalize_choice(normalized.get("fuel_type"), FUEL_MAP))
    set_field("body_type", normalize_choice(normalized.get("body_type"), BODY_MAP))
    set_field("color", normalize_color(normalized.get("color")))
    set_field("seller_type", normalize_choice(normalized.get("seller_type"), SELLER_MAP))
    existing_paint_status = clean_text(normalized.get("paint_status"))
    existing_changed_status = clean_text(normalized.get("changed_part_status"))
    existing_damage_status = clean_text(normalized.get("damage_status"))
    existing_is_clean_claimed = normalize_bool_int(normalized.get("is_clean_claimed"))
    title_paint_status, title_changed_status, title_damage_status = infer_clean_claim_from_title(normalized.get("title"))
    set_field("paint_status", existing_paint_status or title_paint_status)
    set_field("changed_part_status", existing_changed_status or title_changed_status)
    set_field("damage_status", existing_damage_status or title_damage_status)
    set_field("is_clean_claimed", 1 if existing_is_clean_claimed or title_damage_status else 0)
    if "scrape_segment" in normalized:
        set_field("scrape_segment", clean_text(normalized.get("scrape_segment")))

    for column in ["engine", "listing_date", "listing_url", "image_url", "source_listing_id"]:
        if column in normalized:
            set_field(column, clean_text(normalized.get(column)))

    original_city = clean_text(row.get("city"))
    original_district = clean_text(row.get("district"))
    city, district = normalize_location(original_city, original_district)
    set_field("city", city)
    set_field("district", district)
    location_changed = city != original_city or district != original_district

    return normalized, changed_fields, brand_changed, location_changed, brand_page_fields_shifted


def duplicate_keys(row: dict[str, Any]) -> list[tuple[str, ...]]:
    keys: list[tuple[str, ...]] = []
    source = clean_text(row.get("source")) or ""
    source_listing_id = clean_text(row.get("source_listing_id"))
    if source_listing_id:
        keys.append(("source_id", source, source_listing_id))

    listing_url = clean_text(row.get("listing_url"))
    if listing_url:
        keys.append(("url", listing_url.casefold()))

    natural = "|".join(
        [
            normalize_key(row.get("title")),
            normalize_key(row.get("brand")),
            normalize_key(row.get("series")),
            normalize_key(row.get("model")),
            str(row.get("year") or ""),
            str(row.get("mileage_km") or ""),
            str(row.get("price") or ""),
        ]
    )
    keys.append(("natural", natural))
    return keys


def interpolated_quantile(sorted_values: list[int], quantile: float) -> float:
    """Return a linear-interpolated quantile without an extra runtime dependency."""
    if not sorted_values:
        raise ValueError("Cannot calculate a quantile for an empty value list.")

    position = (len(sorted_values) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    fraction = position - lower
    return float(sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * fraction)


def extreme_model_price_outlier_ids(
    rows: list[dict[str, Any]],
    policy: ModelOutlierPolicy | None = None,
) -> set[int]:
    """Find only placeholder-like prices within sufficiently large exact model groups."""
    active_policy = policy or ModelOutlierPolicy()
    groups: dict[tuple[str, str, str], list[tuple[int, int]]] = {}
    for row in rows:
        listing_id = normalize_int(row.get("id"))
        price = normalize_int(row.get("price"))
        brand = clean_text(row.get("brand"))
        series = clean_text(row.get("series"))
        model = clean_text(row.get("model"))
        if listing_id is None or price is None or not brand or not series or not model:
            continue
        groups.setdefault((brand, series, model), []).append((listing_id, price))

    outlier_ids: set[int] = set()
    for members in groups.values():
        if len(members) < active_policy.min_group_size:
            continue
        prices = sorted(price for _, price in members)
        upper_bound = active_policy.upper_price_bound(prices)
        outlier_ids.update(listing_id for listing_id, price in members if price > upper_bound)
    return outlier_ids


def table_columns(connection: sqlite3.Connection, table: str) -> list[str]:
    return [str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")]


def reset_output_tables(connection: sqlite3.Connection, raw_columns: list[str]) -> None:
    connection.execute(f"DROP TABLE IF EXISTS {CLEAN_TABLE}")
    connection.execute(f"DROP TABLE IF EXISTS {REJECTED_TABLE}")
    connection.execute(f"DROP TABLE IF EXISTS {REPORT_TABLE}")
    connection.execute(f"CREATE TABLE {CLEAN_TABLE} AS SELECT * FROM {RAW_TABLE} WHERE 0")
    connection.execute(
        f"""
        CREATE TABLE {REJECTED_TABLE} AS
        SELECT *, CAST(NULL AS TEXT) AS rejection_reason
        FROM {RAW_TABLE}
        WHERE 0
        """
    )
    connection.execute(
        f"""
        CREATE TABLE {REPORT_TABLE} (
            metric TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )

    connection.execute(f"CREATE INDEX IF NOT EXISTS idx_{CLEAN_TABLE}_brand ON {CLEAN_TABLE}(brand)")
    connection.execute(f"CREATE INDEX IF NOT EXISTS idx_{CLEAN_TABLE}_series ON {CLEAN_TABLE}(series)")
    connection.execute(f"CREATE INDEX IF NOT EXISTS idx_{CLEAN_TABLE}_model ON {CLEAN_TABLE}(model)")
    connection.execute(f"CREATE INDEX IF NOT EXISTS idx_{CLEAN_TABLE}_city ON {CLEAN_TABLE}(city)")
    connection.execute(f"CREATE INDEX IF NOT EXISTS idx_{CLEAN_TABLE}_price ON {CLEAN_TABLE}(price)")
    connection.execute(f"CREATE INDEX IF NOT EXISTS idx_{CLEAN_TABLE}_year ON {CLEAN_TABLE}(year)")
    connection.execute(f"CREATE INDEX IF NOT EXISTS idx_{REJECTED_TABLE}_reason ON {REJECTED_TABLE}(rejection_reason)")
    connection.commit()


def reject_reason(row: dict[str, Any], rules: CleanRules, known_brand_keys: set[str], seen: set[tuple[str, ...]]) -> str | None:
    if "is_active" in row and row.get("is_active") is not None and int(row["is_active"]) == 0:
        return "inactive_listing"

    if any(key in seen for key in duplicate_keys(row)):
        return "duplicate_listing"

    price = row.get("price")
    year = row.get("year")
    mileage = row.get("mileage_km")
    brand = row.get("brand")

    if price is None or int(price) <= 0:
        return "missing_price"
    if int(price) < rules.min_price:
        return "price_too_low"
    if int(price) > rules.max_price:
        return "price_too_high"
    if year is None:
        return "missing_year"
    if int(year) < rules.min_year:
        return "year_too_old"
    if int(year) > rules.max_year:
        return "year_in_future"
    if mileage is not None and int(mileage) > rules.max_mileage:
        return "mileage_too_high"
    if not brand or normalize_key(brand) not in known_brand_keys:
        return "unknown_brand"
    if normalize_key(brand) == "tofas" and normalize_key(row.get("series")) not in TOFAS_SERIES_BY_KEY:
        return "unknown_tofas_series"
    if not clean_text(row.get("title")):
        return "missing_title"
    return None


def insert_row(connection: sqlite3.Connection, table: str, columns: list[str], row: dict[str, Any]) -> None:
    placeholders = ", ".join(f":{column}" for column in columns)
    column_sql = ", ".join(columns)
    payload = {column: row.get(column) for column in columns}
    connection.execute(f"INSERT INTO {table} ({column_sql}) VALUES ({placeholders})", payload)


def insert_rejected(
    connection: sqlite3.Connection,
    columns: list[str],
    row: dict[str, Any],
    reason: str,
) -> None:
    rejected_columns = columns + ["rejection_reason"]
    payload = dict(row)
    payload["rejection_reason"] = reason
    insert_row(connection, REJECTED_TABLE, rejected_columns, payload)


def reject_extreme_model_price_outliers(
    connection: sqlite3.Connection,
    raw_columns: list[str],
    policy: ModelOutlierPolicy,
) -> int:
    """Move only extreme relative-price anomalies from clean output to rejected output."""
    if "id" not in raw_columns:
        return 0

    rows = [
        dict(row)
        for row in connection.execute(
            f"SELECT id, brand, series, model, price FROM {CLEAN_TABLE}"
        )
    ]
    outlier_ids = extreme_model_price_outlier_ids(rows, policy)
    for listing_id in sorted(outlier_ids):
        row = connection.execute(
            f"SELECT * FROM {CLEAN_TABLE} WHERE id = ?", (listing_id,)
        ).fetchone()
        if row is None:
            continue
        insert_rejected(connection, raw_columns, dict(row), "model_price_outlier")
        connection.execute(f"DELETE FROM {CLEAN_TABLE} WHERE id = ?", (listing_id,))
    return len(outlier_ids)


def standardize_cosmetic_name_variants(
    connection: sqlite3.Connection,
    columns: list[str],
) -> dict[str, int]:
    """Merge only cosmetic series/model variants in the derived clean table.

    Case, whitespace and hyphen variations are consolidated for selector
    quality. Other punctuation is deliberately retained so package variants
    such as ``AMG`` and ``AMG+`` never collapse into one another.
    """
    updated_by_column: dict[str, int] = {}
    for column in ("series", "model"):
        if column not in columns:
            continue

        groups: dict[str, list[tuple[str, int]]] = {}
        rows = connection.execute(
            f"SELECT TRIM({column}), COUNT(*) FROM {CLEAN_TABLE} "
            f"WHERE {column} IS NOT NULL AND TRIM({column}) <> '' "
            f"GROUP BY TRIM({column})"
        )
        for value, count in rows:
            groups.setdefault(cosmetic_variant_key(value), []).append((str(value), int(count)))

        updated = 0
        for variants in groups.values():
            if len(variants) < 2:
                continue

            canonical, _ = sorted(variants, key=lambda item: (-item[1], item[0].casefold()))[0]
            for value, count in variants:
                if value == canonical:
                    continue
                connection.execute(
                    f"UPDATE {CLEAN_TABLE} SET {column} = ? WHERE {column} = ?",
                    (canonical, value),
                )
                updated += count
        updated_by_column[column] = updated
    return updated_by_column


def write_report(connection: sqlite3.Connection, metrics: dict[str, Any]) -> None:
    rows = [(key, str(value)) for key, value in sorted(metrics.items())]
    connection.executemany(
        f"INSERT INTO {REPORT_TABLE} (metric, value) VALUES (?, ?)",
        rows,
    )


def missing_counts(connection: sqlite3.Connection, columns: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for column in columns:
        row = connection.execute(
            f"SELECT COUNT(*) FROM {CLEAN_TABLE} WHERE {column} IS NULL OR TRIM(CAST({column} AS TEXT)) = ''"
        ).fetchone()
        counts[f"missing_{column}"] = int(row[0])
    return counts


def clean_database(db_path: Path, catalog_path: Path, rules: CleanRules) -> CleanResult:
    brand_map = load_catalog_brands(catalog_path)
    known_brand_keys = {normalize_key(value) for value in brand_map.values()}
    rejection_counts: Counter[str] = Counter()
    seen_keys: set[tuple[str, ...]] = set()

    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        raw_columns = table_columns(connection, RAW_TABLE)
        reset_output_tables(connection, raw_columns)

        raw_total = 0
        clean_total = 0
        rejected_total = 0
        duplicate_total = 0
        normalized_field_total = 0
        corrected_brand_total = 0
        corrected_location_total = 0
        corrected_brand_page_field_total = 0

        order_by = "datetime(scraped_at) DESC, id DESC" if "id" in raw_columns else "datetime(scraped_at) DESC"
        rows = connection.execute(f"SELECT * FROM {RAW_TABLE} ORDER BY {order_by}")
        for sqlite_row in rows:
            raw_total += 1
            row, changed_fields, brand_changed, location_changed, brand_page_fields_shifted = normalize_row(
                dict(sqlite_row),
                brand_map,
            )
            normalized_field_total += changed_fields
            if brand_changed:
                corrected_brand_total += 1
            if location_changed:
                corrected_location_total += 1
            if brand_page_fields_shifted:
                corrected_brand_page_field_total += 1

            reason = reject_reason(row, rules, known_brand_keys, seen_keys)
            if reason:
                rejection_counts[reason] += 1
                if reason == "duplicate_listing":
                    duplicate_total += 1
                insert_rejected(connection, raw_columns, row, reason)
                rejected_total += 1
                continue

            seen_keys.update(duplicate_keys(row))
            insert_row(connection, CLEAN_TABLE, raw_columns, row)
            clean_total += 1

        canonicalized_variants = standardize_cosmetic_name_variants(connection, raw_columns)

        relative_outlier_total = reject_extreme_model_price_outliers(
            connection,
            raw_columns,
            rules.model_outlier_policy,
        )
        if relative_outlier_total:
            rejection_counts["model_price_outlier"] += relative_outlier_total
            rejected_total += relative_outlier_total
            clean_total -= relative_outlier_total

        metrics: dict[str, Any] = {
            "raw_total": raw_total,
            "clean_total": clean_total,
            "rejected_total": rejected_total,
            "duplicate_total": duplicate_total,
            "normalized_field_total": normalized_field_total,
            "corrected_brand_total": corrected_brand_total,
            "corrected_location_total": corrected_location_total,
            "corrected_brand_page_field_total": corrected_brand_page_field_total,
            "canonicalized_series_variant_total": canonicalized_variants.get("series", 0),
            "canonicalized_model_variant_total": canonicalized_variants.get("model", 0),
        }
        metrics.update({f"rejected_{reason}": total for reason, total in rejection_counts.items()})
        metrics.update(
            missing_counts(
                connection,
                [
                    "brand",
                    "series",
                    "model",
                    "year",
                    "mileage_km",
                    "transmission",
                    "fuel_type",
                    "body_type",
                    "color",
                    "city",
                    "district",
                    "seller_type",
                    "price",
                ],
            )
        )
        write_report(connection, metrics)
        connection.commit()

    return CleanResult(
        raw_total=raw_total,
        clean_total=clean_total,
        rejected_total=rejected_total,
        duplicate_total=duplicate_total,
        normalized_field_total=normalized_field_total,
        corrected_brand_total=corrected_brand_total,
        corrected_location_total=corrected_location_total,
        corrected_brand_page_field_total=corrected_brand_page_field_total,
        canonicalized_series_variant_total=canonicalized_variants.get("series", 0),
        canonicalized_model_variant_total=canonicalized_variants.get("model", 0),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create cleaned and normalized vehicle listing tables.")
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--catalog-path", default=str(CATALOG_PATH))
    parser.add_argument("--min-price", type=int, default=DEFAULT_MIN_PRICE)
    parser.add_argument("--max-price", type=int, default=DEFAULT_MAX_PRICE)
    parser.add_argument("--min-year", type=int, default=DEFAULT_MIN_YEAR)
    parser.add_argument("--max-year", type=int, default=default_max_year())
    parser.add_argument("--max-mileage", type=int, default=DEFAULT_MAX_MILEAGE)
    parser.add_argument("--outlier-min-group-size", type=int, default=50)
    parser.add_argument("--outlier-median-multiplier", type=float, default=20.0)
    parser.add_argument("--outlier-iqr-multiplier", type=float, default=3.0)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    rules = CleanRules(
        min_price=args.min_price,
        max_price=args.max_price,
        min_year=args.min_year,
        max_year=args.max_year,
        max_mileage=args.max_mileage,
        model_outlier_policy=ModelOutlierPolicy(
            min_group_size=args.outlier_min_group_size,
            median_multiplier=args.outlier_median_multiplier,
            iqr_multiplier=args.outlier_iqr_multiplier,
        ),
    )
    result = clean_database(Path(args.db_path), Path(args.catalog_path), rules)
    print(f"raw_total={result.raw_total}")
    print(f"clean_total={result.clean_total}")
    print(f"rejected_total={result.rejected_total}")
    print(f"duplicate_total={result.duplicate_total}")
    print(f"normalized_field_total={result.normalized_field_total}")
    print(f"corrected_brand_total={result.corrected_brand_total}")
    print(f"corrected_location_total={result.corrected_location_total}")
    print(f"corrected_brand_page_field_total={result.corrected_brand_page_field_total}")
    print(f"canonicalized_series_variant_total={result.canonicalized_series_variant_total}")
    print(f"canonicalized_model_variant_total={result.canonicalized_model_variant_total}")


if __name__ == "__main__":
    main()
