"""Import the monthly TSB kasko reference value list.

This is the project's automatable data backbone. Unlike listing ingestion it
needs no browser and no access check: the Insurance Association of Turkey
publishes a value list per period, and importing it is an ordinary file read.

The published workbook's exact header text is not contracted anywhere, so the
columns are detected from a set of known Turkish spellings and can always be
overridden explicitly. An unrecognised layout fails loudly with the headers it
actually saw, rather than silently importing the wrong column.

The values are insurance reference values, not asking prices. They are stored
in their own table and never mixed into the listing tables.
"""

from __future__ import annotations

import argparse
import logging
import re
import sqlite3
import unicodedata
from collections.abc import Iterable
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

REFERENCE_TABLE = "reference_vehicle_values"
SOURCE_TSB = "tsb_kasko"

# Accepted spellings per logical column, normalized (lowercase, no diacritics).
COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "vehicle_code": ("arac kodu", "araç kodu", "kod", "arac kod", "tsb kodu"),
    "brand": ("marka", "marka adi", "marka adı"),
    "model_name": ("tip", "tip adi", "tip adı", "model", "model adi", "model adı", "tip aciklama"),
    "model_year": ("model yili", "model yılı", "model yil", "yil", "yıl"),
    "reference_value": (
        "kasko degeri", "kasko değeri", "kasko bedeli", "kasko deger", "deger", "değer", "bedel",
    ),
}
REQUIRED_COLUMNS = ("brand", "model_name", "model_year", "reference_value")

PERIOD_PATTERN = re.compile(r"(20\d{2})[-_ ]?(0[1-9]|1[0-2])")
MONTH_NAMES = {
    "ocak": 1, "subat": 2, "mart": 3, "nisan": 4, "mayis": 5, "haziran": 6,
    "temmuz": 7, "agustos": 8, "eylul": 9, "ekim": 10, "kasim": 11, "aralik": 12,
}


@dataclass(frozen=True, slots=True)
class ImportResult:
    """Outcome of importing one period's list."""

    period: str
    rows_read: int
    rows_imported: int
    source_path: str

    def __str__(self) -> str:
        return f"period={self.period} rows_read={self.rows_read} rows_imported={self.rows_imported}"


class ReferenceListError(RuntimeError):
    """Raised when a published list cannot be read with confidence."""


def normalize_header(value: object) -> str:
    text = str(value if value is not None else "").strip().casefold()
    text = text.replace("ı", "i").replace("İ", "i")
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", text)


def detect_columns(headers: Iterable[object], overrides: dict[str, str] | None = None) -> dict[str, str]:
    """Map logical names to the workbook's actual column labels."""
    overrides = overrides or {}
    original = list(headers)
    normalized = {normalize_header(header): header for header in original}

    mapping: dict[str, str] = {}
    for logical, aliases in COLUMN_ALIASES.items():
        if logical in overrides:
            wanted = overrides[logical]
            if wanted not in original:
                raise ReferenceListError(f"Belirtilen sutun bulunamadi: {wanted!r}. Mevcut sutunlar: {original}")
            mapping[logical] = wanted
            continue
        for alias in aliases:
            match = normalized.get(normalize_header(alias))
            if match is not None:
                mapping[logical] = match
                break

    missing = [name for name in REQUIRED_COLUMNS if name not in mapping]
    if missing:
        raise ReferenceListError(
            "Kasko listesinde su sutunlar taninamadi: "
            f"{', '.join(missing)}. Dosyadaki sutunlar: {original}. "
            "--column ile acikca eslestirebilirsiniz."
        )
    return mapping


def parse_turkish_number(value: object) -> float | None:
    """Read a value written as 1.234.567 or 1.234.567,89 or a plain number."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if number > 0 else None

    text = str(value).strip()
    if not text:
        return None
    text = re.sub(r"[^\d,.\-]", "", text)
    if not text:
        return None
    if "," in text:
        # Turkish decimal comma: dots are thousands separators.
        text = text.replace(".", "").replace(",", ".")
    elif text.count(".") > 1 or re.fullmatch(r"\d{1,3}(\.\d{3})+", text):
        text = text.replace(".", "")
    try:
        number = float(text)
    except ValueError:
        return None
    return number if number > 0 else None


def period_from_name(name: str) -> str | None:
    """Derive a YYYY-MM period from a file name, or return None."""
    normalized = normalize_header(name)
    match = PERIOD_PATTERN.search(normalized)
    if match:
        return f"{match.group(1)}-{match.group(2)}"
    year_match = re.search(r"20\d{2}", normalized)
    if year_match:
        for month_name, month in MONTH_NAMES.items():
            if month_name in normalized:
                return f"{year_match.group(0)}-{month:02d}"
    return None


def ensure_reference_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {REFERENCE_TABLE} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            period TEXT NOT NULL,
            vehicle_code TEXT,
            brand TEXT NOT NULL,
            model_name TEXT NOT NULL,
            model_year INTEGER NOT NULL,
            reference_value REAL NOT NULL,
            loaded_at TEXT NOT NULL,
            UNIQUE(source, period, brand, model_name, model_year)
        )
        """
    )
    connection.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{REFERENCE_TABLE}_lookup "
        f"ON {REFERENCE_TABLE}(brand, model_year, period)"
    )
    connection.commit()


def read_reference_frame(path: Path, overrides: dict[str, str] | None = None) -> pd.DataFrame:
    """Read one published list into normalized columns."""
    if not path.exists():
        raise ReferenceListError(f"Kasko listesi bulunamadi: {path}")

    suffix = path.suffix.casefold()
    if suffix in {".xlsx", ".xlsm"}:
        frame = pd.read_excel(path, dtype=object)
    elif suffix in {".csv", ".txt"}:
        frame = pd.read_csv(path, dtype=object, sep=None, engine="python")
    else:
        raise ReferenceListError(f"Desteklenmeyen dosya turu: {path.suffix}")

    mapping = detect_columns(frame.columns, overrides)
    selected = pd.DataFrame(
        {logical: frame[column] for logical, column in mapping.items()}
    )
    if "vehicle_code" not in selected:
        selected["vehicle_code"] = None

    selected["brand"] = selected["brand"].astype(str).str.strip()
    selected["model_name"] = selected["model_name"].astype(str).str.strip()
    selected["model_year"] = pd.to_numeric(selected["model_year"], errors="coerce")
    selected["reference_value"] = selected["reference_value"].map(parse_turkish_number)
    selected["vehicle_code"] = selected["vehicle_code"].map(
        lambda value: str(value).strip() if value is not None and str(value).strip() not in {"", "nan"} else None
    )

    selected = selected[
        selected["brand"].ne("")
        & selected["brand"].str.casefold().ne("nan")
        & selected["model_name"].ne("")
        & selected["model_year"].notna()
        & selected["reference_value"].notna()
    ]
    return selected.reset_index(drop=True)


def import_reference_file(
    path: Path,
    db_path: Path,
    period: str | None = None,
    overrides: dict[str, str] | None = None,
) -> ImportResult:
    """Import one period's list, replacing that period's rows if re-imported."""
    resolved_period = period or period_from_name(path.name)
    if not resolved_period:
        raise ReferenceListError(
            f"Donem belirlenemedi: {path.name}. --period YYYY-MM ile acikca verin."
        )

    frame = read_reference_frame(path, overrides)
    rows = [
        (
            SOURCE_TSB, resolved_period, row.vehicle_code, row.brand, row.model_name,
            int(row.model_year), float(row.reference_value), datetime.now(UTC).isoformat(),
        )
        for row in frame.itertuples(index=False)
    ]

    with closing(sqlite3.connect(db_path)) as connection:
        ensure_reference_table(connection)
        connection.executemany(
            f"""INSERT INTO {REFERENCE_TABLE}
                (source, period, vehicle_code, brand, model_name, model_year, reference_value, loaded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source, period, brand, model_name, model_year)
                DO UPDATE SET reference_value=excluded.reference_value,
                              vehicle_code=COALESCE(excluded.vehicle_code, vehicle_code),
                              loaded_at=excluded.loaded_at""",
            rows,
        )
        connection.commit()

    return ImportResult(
        period=resolved_period,
        rows_read=int(len(frame)),
        rows_imported=len(rows),
        source_path=str(path),
    )


def imported_periods(connection: sqlite3.Connection) -> set[str]:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (REFERENCE_TABLE,)
    ).fetchone()
    if row is None:
        return set()
    return {
        str(item[0])
        for item in connection.execute(f"SELECT DISTINCT period FROM {REFERENCE_TABLE} WHERE source = ?", (SOURCE_TSB,))
    }


def import_new_files(directory: Path, db_path: Path) -> list[ImportResult]:
    """Import every published list in ``directory`` that is not stored yet."""
    if not directory.exists():
        return []

    with closing(sqlite3.connect(db_path)) as connection:
        already = imported_periods(connection)

    results: list[ImportResult] = []
    for path in sorted(directory.iterdir()):
        if path.suffix.casefold() not in {".xlsx", ".xlsm", ".csv", ".txt"} or path.name.startswith("~$"):
            continue
        period = period_from_name(path.name)
        if period and period in already:
            continue
        results.append(import_reference_file(path, db_path, period))
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TSB kasko deger listesini iceri aktar.")
    parser.add_argument("path", type=Path, help="Aylik liste dosyasi veya dizin")
    parser.add_argument("--db-path", type=Path, required=True)
    parser.add_argument("--period", default=None, help="YYYY-MM; dosya adindan cikarilamazsa gerekir")
    parser.add_argument(
        "--column", action="append", default=[], metavar="LOGICAL=SUTUN",
        help="Sutun eslemesini acikca ver, orn. --column reference_value='Kasko Bedeli'",
    )
    args = parser.parse_args(argv)

    overrides: dict[str, str] = {}
    for item in args.column:
        logical, _, column = item.partition("=")
        if not column:
            parser.error(f"Gecersiz --column degeri: {item}")
        overrides[logical.strip()] = column.strip()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.path.is_dir():
        results = import_new_files(args.path, args.db_path)
        if not results:
            print("Yeni donem bulunamadi.")
            return 0
    else:
        results = [import_reference_file(args.path, args.db_path, args.period, overrides)]

    for result in results:
        print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
