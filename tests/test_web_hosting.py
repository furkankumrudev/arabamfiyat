from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.main import mount_web_app


class SingleContainerHostingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        dist = Path(self.temp_dir.name) / "dist"
        (dist / "assets").mkdir(parents=True)
        (dist / "index.html").write_text("<div id=root></div>", encoding="utf-8")
        (dist / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
        (dist / "favicon.svg").write_text("<svg/>", encoding="utf-8")
        (Path(self.temp_dir.name) / "secret.txt").write_text("secret", encoding="utf-8")

        application = FastAPI()

        @application.get("/api/ping")
        def ping() -> dict[str, str]:
            return {"status": "ok"}

        mount_web_app(application, dist)
        self.client = TestClient(application)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_api_routes_still_win(self) -> None:
        self.assertEqual(self.client.get("/api/ping").json(), {"status": "ok"})

    def test_unknown_api_path_is_a_404_not_the_web_app(self) -> None:
        self.assertEqual(self.client.get("/api/nope").status_code, 404)

    def test_client_side_routes_get_the_app_shell(self) -> None:
        for path in ("/", "/arac-degerleme", "/piyasa-trendleri"):
            with self.subTest(path=path):
                self.assertIn("root", self.client.get(path).text)

    def test_built_files_are_served(self) -> None:
        self.assertEqual(self.client.get("/assets/app.js").text, "console.log(1)")
        self.assertEqual(self.client.get("/favicon.svg").text, "<svg/>")

    def test_files_outside_the_build_are_not_reachable(self) -> None:
        self.assertNotIn("secret", self.client.get("/..%2Fsecret.txt").text)


if __name__ == "__main__":
    unittest.main()
