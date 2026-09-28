from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

import pandas as pd

from src.ingestion.tsb_reference import (
    REFERENCE_TABLE,
    ImportResult,
    ReferenceListError,
    detect_columns,
    import_new_files,
    import_reference_file,
    parse_turkish_number,
    period_from_name,
    read_reference_frame,
)

# Headers as the published workbook is expected to spell them. The exact text is
# not contracted by TSB, which is why detection accepts several spellings.
SHEET_ROWS = [
    {"Araç Kodu": "9-1616", "Marka": "AUDI", "Tip": "A3 SPORTBACK 35 TFSI", "Model Yılı": 2021, "Kasko Değeri": "1.850.000"},
    {"Araç Kodu": "9-1617", "Marka": "AUDI", "Tip": "A4 2.0 TDI", "Model Yılı": 2020, "Kasko Değeri": "2.100.500,50"},
    {"Araç Kodu": "5-201", "Marka": "FIAT", "Tip": "EGEA 1.4 FIRE", "Model Yılı": 2021, "Kasko Değeri": 950000},
]


def write_workbook(path: Path, rows: list[dict[str, object]]) -> Path:
    pd.DataFrame(rows).to_excel(path, index=False)
    return path


class NumberParsingTests(unittest.TestCase):
    def test_thousands_separated_value(self) -> None:
        self.assertEqual(parse_turkish_number("1.850.000"), 1_850_000.0)

    def test_decimal_comma_value(self) -> None:
        self.assertEqual(parse_turkish_number("2.100.500,50"), 2_100_500.5)

    def test_plain_number_passes_through(self) -> None:
        self.assertEqual(parse_turkish_number(950000), 950_000.0)

    def test_currency_decoration_is_ignored(self) -> None:
        self.assertEqual(parse_turkish_number("1.250.000 TL"), 1_250_000.0)

    def test_unusable_values_are_rejected_rather_than_guessed(self) -> None:
        for value in (None, "", "-", "yok", 0, -5):
            with self.subTest(value=value):
                self.assertIsNone(parse_turkish_number(value))


class ColumnDetectionTests(unittest.TestCase):
    def test_detects_standard_headers(self) -> None:
        mapping = detect_columns(["Araç Kodu", "Marka", "Tip", "Model Yılı", "Kasko Değeri"])

        self.assertEqual(mapping["brand"], "Marka")
        self.assertEqual(mapping["model_year"], "Model Yılı")
        self.assertEqual(mapping["reference_value"], "Kasko Değeri")

    def test_detection_ignores_case_spacing_and_diacritics(self) -> None:
        mapping = detect_columns(["MARKA", "  model adi ", "MODEL YILI", "kasko bedeli"])

        self.assertEqual(mapping["model_name"], "  model adi ")
        self.assertEqual(mapping["reference_value"], "kasko bedeli")

    def test_unknown_layout_fails_loudly_and_shows_the_headers(self) -> None:
        with self.assertRaises(ReferenceListError) as caught:
            detect_columns(["A", "B", "C"])

        message = str(caught.exception)
        self.assertIn("brand", message)
        self.assertIn("'A'", message)

    def test_explicit_override_wins(self) -> None:
        mapping = detect_columns(
            ["Marka", "Tip", "Model Yılı", "Kasko Değeri", "Özel Bedel"],
            overrides={"reference_value": "Özel Bedel"},
        )

        self.assertEqual(mapping["reference_value"], "Özel Bedel")

    def test_override_naming_a_missing_column_is_an_error(self) -> None:
        with self.assertRaises(ReferenceListError):
            detect_columns(["Marka", "Tip", "Model Yılı", "Kasko Değeri"], overrides={"brand": "Yok"})


class PeriodDetectionTests(unittest.TestCase):
    def test_numeric_period_in_file_name(self) -> None:
        self.assertEqual(period_from_name("kasko_2026_09.xlsx"), "2026-09")
        self.assertEqual(period_from_name("Kasko-2026-01.xlsx"), "2026-01")

    def test_turkish_month_name_in_file_name(self) -> None:
        self.assertEqual(period_from_name("Kasko Değer Listesi Eylül 2026.xlsx"), "2026-09")

    def test_undetectable_name_returns_none_instead_of_guessing(self) -> None:
        self.assertIsNone(period_from_name("liste.xlsx"))


class ReferenceImportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.db_path = self.root / "listings.sqlite3"
        self.list_path = write_workbook(self.root / "kasko_2026_09.xlsx", SHEET_ROWS)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _stored(self) -> list[tuple]:
        with closing(sqlite3.connect(self.db_path)) as connection:
            return connection.execute(
                f"SELECT brand, model_name, model_year, reference_value, period FROM {REFERENCE_TABLE} ORDER BY id"
            ).fetchall()

    def test_frame_keeps_only_usable_rows(self) -> None:
        path = write_workbook(
            self.root / "kasko_2026_08.xlsx",
            SHEET_ROWS + [{"Araç Kodu": "x", "Marka": "", "Tip": "", "Model Yılı": None, "Kasko Değeri": "-"}],
        )

        frame = read_reference_frame(path)

        self.assertEqual(len(frame), 3)

    def test_import_stores_every_row_with_its_period(self) -> None:
        result = import_reference_file(self.list_path, self.db_path)

        self.assertIsInstance(result, ImportResult)
        self.assertEqual(result.period, "2026-09")
        self.assertEqual(result.rows_imported, 3)
        stored = self._stored()
        self.assertEqual(len(stored), 3)
        self.assertEqual(stored[0][0], "AUDI")
        self.assertEqual(stored[0][3], 1_850_000.0)
        self.assertEqual(stored[0][4], "2026-09")

    def test_reimporting_the_same_period_updates_instead_of_duplicating(self) -> None:
        import_reference_file(self.list_path, self.db_path)
        revised = [dict(row) for row in SHEET_ROWS]
        revised[0]["Kasko Değeri"] = "1.900.000"
        write_workbook(self.list_path, revised)

        import_reference_file(self.list_path, self.db_path)

        stored = self._stored()
        self.assertEqual(len(stored), 3)
        self.assertEqual(stored[0][3], 1_900_000.0)

    def test_periods_accumulate_side_by_side(self) -> None:
        import_reference_file(self.list_path, self.db_path)
        august = write_workbook(self.root / "kasko_2026_08.xlsx", SHEET_ROWS)

        import_reference_file(august, self.db_path)

        periods = {row[4] for row in self._stored()}
        self.assertEqual(periods, {"2026-08", "2026-09"})
        self.assertEqual(len(self._stored()), 6)

    def test_an_undetectable_period_is_refused_rather_than_assumed(self) -> None:
        path = write_workbook(self.root / "liste.xlsx", SHEET_ROWS)

        with self.assertRaises(ReferenceListError):
            import_reference_file(path, self.db_path)

    def test_explicit_period_overrides_the_file_name(self) -> None:
        path = write_workbook(self.root / "liste.xlsx", SHEET_ROWS)

        result = import_reference_file(path, self.db_path, period="2026-07")

        self.assertEqual(result.period, "2026-07")

    def test_missing_file_is_reported_clearly(self) -> None:
        with self.assertRaises(ReferenceListError):
            import_reference_file(self.root / "yok.xlsx", self.db_path)


class DirectoryImportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.db_path = self.root / "listings.sqlite3"
        self.inbox = self.root / "kasko"
        self.inbox.mkdir()
        write_workbook(self.inbox / "kasko_2026_08.xlsx", SHEET_ROWS)
        write_workbook(self.inbox / "kasko_2026_09.xlsx", SHEET_ROWS)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_first_run_imports_every_period(self) -> None:
        results = import_new_files(self.inbox, self.db_path)

        self.assertEqual({result.period for result in results}, {"2026-08", "2026-09"})

    def test_second_run_skips_periods_already_stored(self) -> None:
        import_new_files(self.inbox, self.db_path)

        self.assertEqual(import_new_files(self.inbox, self.db_path), [])

    def test_only_a_newly_published_period_is_imported(self) -> None:
        import_new_files(self.inbox, self.db_path)
        write_workbook(self.inbox / "kasko_2026_10.xlsx", SHEET_ROWS)

        results = import_new_files(self.inbox, self.db_path)

        self.assertEqual([result.period for result in results], ["2026-10"])

    def test_missing_directory_is_not_an_error(self) -> None:
        self.assertEqual(import_new_files(self.root / "yok", self.db_path), [])

    def test_excel_lock_files_are_ignored(self) -> None:
        (self.inbox / "~$kasko_2026_11.xlsx").write_bytes(b"lock")

        results = import_new_files(self.inbox, self.db_path)

        self.assertNotIn("2026-11", {result.period for result in results})


if __name__ == "__main__":
    unittest.main()
