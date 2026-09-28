"""Check whether stored Sahibinden listing URLs are still active."""

from __future__ import annotations

import argparse
import asyncio
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from src.experimental.sahibinden.category_page_scraper import (
    find_browser_executable,
    has_access_challenge,
    has_login_page,
)
from src.experimental.sahibinden.scraper import ScraperConfig, start_browser, wait_for_manual_access_check
from src.ingestion.storage import DEFAULT_DB_PATH

SCRAPER_PROFILE_PATH = Path("data") / "runtime" / "edge-profile-status"

REMOVED_MARKERS = (
    "ilan yayından kaldırılmış",
    "ilan yayından kaldırıldı",
    "bu ilan yayında değildir",
    "bu ilan artık yayında değil",
    "aradığınız ilan yayından kaldırılmış",
    "aradığınız sayfa bulunamadı",
    "ilan bulunamadı",
)

ACTIVE_MARKERS = (
    "classifiedDetail",
    "classifiedId",
    "classifiedInfo",
    "İlan No",
    "İlan Tarihi",
)


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def ensure_status_columns(connection: sqlite3.Connection) -> None:
    existing = {str(row[1]) for row in connection.execute("PRAGMA table_info(vehicle_listings)")}
    additions = {
        "is_active": "INTEGER DEFAULT 1",
        "status_checked_at": "TEXT",
        "removed_at": "TEXT",
        "status_reason": "TEXT",
    }
    for column, sql_type in additions.items():
        if column not in existing:
            connection.execute(f"ALTER TABLE vehicle_listings ADD COLUMN {column} {sql_type}")
    connection.commit()


def fetch_candidates(connection: sqlite3.Connection, limit: int) -> list[sqlite3.Row]:
    connection.row_factory = sqlite3.Row
    return list(
        connection.execute(
            """
            SELECT id, source_listing_id, title, listing_url, status_checked_at
            FROM vehicle_listings
            WHERE listing_url IS NOT NULL
              AND trim(listing_url) != ''
              AND coalesce(is_active, 1) = 1
            ORDER BY
              status_checked_at IS NOT NULL,
              status_checked_at ASC,
              scraped_at ASC
            LIMIT ?
            """,
            (limit,),
        )
    )


def classify_html(html: str) -> tuple[str, str]:
    normalized = html.casefold()
    if has_access_challenge(html):
        return "unknown", "access_challenge"
    if has_login_page(html):
        return "unknown", "login_page"
    if any(marker.casefold() in normalized for marker in REMOVED_MARKERS):
        return "removed", "removed_marker"
    if any(marker.casefold() in normalized for marker in ACTIVE_MARKERS):
        return "active", "active_marker"
    return "unknown", "unrecognized_page"


def update_status(connection: sqlite3.Connection, listing_id: int, status: str, reason: str) -> None:
    checked_at = utc_now()
    if status == "removed":
        connection.execute(
            """
            UPDATE vehicle_listings
            SET is_active = 0,
                status_checked_at = ?,
                removed_at = coalesce(removed_at, ?),
                status_reason = ?
            WHERE id = ?
            """,
            (checked_at, checked_at, reason, listing_id),
        )
    elif status == "active":
        connection.execute(
            """
            UPDATE vehicle_listings
            SET is_active = 1,
                status_checked_at = ?,
                removed_at = NULL,
                status_reason = ?
            WHERE id = ?
            """,
            (checked_at, reason, listing_id),
        )
    else:
        connection.execute(
            """
            UPDATE vehicle_listings
            SET status_checked_at = ?,
                status_reason = ?
            WHERE id = ?
            """,
            (checked_at, reason, listing_id),
        )
    connection.commit()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Mark removed Sahibinden listings in the local database.")
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--delay-min", type=float, default=2.0)
    parser.add_argument("--delay-max", type=float, default=5.0)
    parser.add_argument("--manual-wait-seconds", type=float, default=120)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--no-sandbox", action="store_true")
    parser.add_argument("--stop-on-access", action="store_true")
    return parser


async def run(args: argparse.Namespace) -> None:
    db_path = Path(args.db_path)
    with sqlite3.connect(db_path) as connection:
        ensure_status_columns(connection)
        candidates = fetch_candidates(connection, args.limit)

    if not candidates:
        print("No active listing URL candidates found.", flush=True)
        return

    config = ScraperConfig(
        query="status-check",
        delay_min=args.delay_min,
        delay_max=args.delay_max,
        db_path=str(db_path),
        headless=args.headless,
        browser_executable_path=find_browser_executable(),
        user_data_dir=str(SCRAPER_PROFILE_PATH),
        sandbox=not args.no_sandbox,
        manual_wait_seconds=args.manual_wait_seconds,
    )
    driver = await start_browser(config)
    counts = {"active": 0, "removed": 0, "unknown": 0}
    try:
        for index, row in enumerate(candidates, start=1):
            url = str(row["listing_url"])
            print(f"[{index}/{len(candidates)}] Checking {row['source_listing_id']} {url}", flush=True)
            tab = await driver.get(url)
            await wait_for_manual_access_check(tab, config, f"checking listing {row['source_listing_id']}")
            html = await tab.get_content()
            status, reason = classify_html(html)
            counts[status] += 1
            with sqlite3.connect(db_path) as connection:
                ensure_status_columns(connection)
                update_status(connection, int(row["id"]), status, reason)
            print(f"status={status} reason={reason}", flush=True)
            if status == "unknown" and reason in {"access_challenge", "login_page"} and args.stop_on_access:
                break
    finally:
        driver.stop()

    print(
        f"checked={sum(counts.values())} active={counts['active']} "
        f"removed={counts['removed']} unknown={counts['unknown']}",
        flush=True,
    )


def main() -> None:
    args = build_parser().parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
