from __future__ import annotations

import unittest

from src.api.database import DEFAULT_DB_PATH as API_DB_PATH
from src.api.settings import sqlite_db_path
from src.ingestion.storage import DEFAULT_DB_PATH as STORAGE_DB_PATH
from src.maintenance.clean_vehicle_data import DEFAULT_DB_PATH as CLEAN_DB_PATH


class DatabasePathTests(unittest.TestCase):
    def test_every_command_uses_the_configured_database(self) -> None:
        """Writers and the API must agree, or new listings never reach the site."""
        self.assertEqual(STORAGE_DB_PATH, sqlite_db_path())
        self.assertEqual(CLEAN_DB_PATH, sqlite_db_path())
        self.assertEqual(API_DB_PATH, sqlite_db_path())


if __name__ == "__main__":
    unittest.main()
