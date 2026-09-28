"""Import listings from a CSV file.

This is the path for data the project is allowed to use: an export from a
partner, a licensed dataset, or listings collected by hand. The file uses the
listing schema's own column names so there is nothing to guess; a file that
lacks a required column is rejected with the headers it actually has.
"""

from __future__ import annotations

import csv
import hashlib
import re
from collections.abc import Iterator
from dataclasses import fields
from pathlib import Path

from src.ingestion.schema import VehicleListing

REQUIRED_COLUMNS = ("title", "brand", "series", "model", "year", "mileage_km", "price")
INTEGER_COLUMNS = {"year", "mileage_km", "price", "is_clean_claimed"}
# Filled in by the loader, never read from the file.
MANAGED_COLUMNS = {"source", "scraped_at"}
ACCEPTED_COLUMNS = {field.name for field in fields(VehicleListing)} - MANAGED_COLUMNS


class CsvFormatError(ValueError):
    """The file cannot be imported as it is."""


def parse_integer(value: str | None) -> int | None:
    """Read integers written the Turkish way, e.g. ``1.250.000 TL`` or ``85.000 km``."""
    digits = re.sub(r"\D", "", value or "")
    return int(digits) if digits else None


def _dialect(sample: str) -> type[csv.Dialect] | csv.Dialect:
    try:
        # Spreadsheet exports in Turkish locales usually separate with ';'.
        return csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        return csv.excel


class CsvSource:
    """Listings read from a CSV file whose headers use the schema's column names."""

    def __init__(self, path: Path, name: str | None = None) -> None:
        self.path = Path(path)
        self.name = name or self.path.stem
        self.skipped_columns: list[str] = []

    def listings(self) -> Iterator[VehicleListing]:
        if not self.path.exists():
            raise CsvFormatError(f"Dosya bulunamadi: {self.path}")
        with self.path.open(encoding="utf-8-sig", newline="") as handle:
            sample = handle.read(4096)
            handle.seek(0)
            reader = csv.DictReader(handle, dialect=_dialect(sample))
            headers = [name.strip() for name in reader.fieldnames or []]
            missing = [column for column in REQUIRED_COLUMNS if column not in headers]
            if missing:
                raise CsvFormatError(
                    f"Zorunlu sutunlar eksik: {', '.join(missing)}. "
                    f"Dosyadaki sutunlar: {', '.join(headers) or '(bos)'}"
                )
            self.skipped_columns = [column for column in headers if column not in ACCEPTED_COLUMNS]
            for row in reader:
                listing = self._listing(row)
                if listing is not None:
                    yield listing

    def _listing(self, row: dict[str, str | None]) -> VehicleListing | None:
        values: dict[str, object] = {}
        for key, value in row.items():
            column = (key or "").strip()
            if column in ACCEPTED_COLUMNS:
                text = value.strip() if isinstance(value, str) else ""
                values[column] = text or None
        if not any(values.values()):
            return None
        for column in INTEGER_COLUMNS & values.keys():
            values[column] = parse_integer(values[column])  # type: ignore[arg-type]
        if not values.get("source_listing_id"):
            # A stable id keeps re-importing the same file idempotent.
            fingerprint = "|".join(f"{column}={values[column]}" for column in sorted(values))
            values["source_listing_id"] = hashlib.sha1(fingerprint.encode("utf-8")).hexdigest()[:16]
        if values.get("is_clean_claimed") is None:
            values.pop("is_clean_claimed", None)
        if values.get("currency") is None:
            values.pop("currency", None)
        values["title"] = values.get("title") or ""
        return VehicleListing.create(source=self.name, **values)  # type: ignore[arg-type]
