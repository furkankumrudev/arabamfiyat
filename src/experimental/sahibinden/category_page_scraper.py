"""Fast page-by-page scraper for Sahibinden automobile category listings."""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import re
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from src.experimental.sahibinden.scraper import (
    ScraperConfig,
    parse_search_results,
    start_browser,
    wait_for_manual_access_check,
)
from src.ingestion.storage import DEFAULT_DB_PATH, ListingStore

BASE_URL = "https://www.sahibinden.com/otomobil"
DEFAULT_CHECKPOINT_PATH = Path("data") / "runtime" / "category_page_checkpoint.json"
DEFAULT_DEBUG_PATH = Path("data") / "runtime" / "debug_category_page.html"
SCRAPER_PROFILE_PATH = Path("data") / "runtime" / "edge-profile-category"
ACCESS_MARKERS = (
    "bağlantınız kontrol ediliyor",
    "basılı tut",
    "olağan dışı erişim",
    "cdn-cgi/challenge-platform",
)
LOGIN_MARKERS = (
    "<title>sahibinden.com giriş</title>",
    "individual-login-body",
    "giriş yapmanız gerekmektedir",
)


def find_browser_executable() -> str | None:
    candidates = [
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


@dataclass(slots=True)
class PageResult:
    offset: int
    parsed: int
    changed: int
    stored_total: int


def load_checkpoint(path: Path) -> int:
    if not path.exists():
        return 0
    data = json.loads(path.read_text(encoding="utf-8"))
    return int(data.get("next_offset", 0))


def save_checkpoint(path: Path, next_offset: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"next_offset": next_offset}, indent=2), encoding="utf-8")


def build_url(offset: int, page_size: int) -> str:
    return f"{BASE_URL}?{urlencode({'pagingSize': page_size, 'pagingOffset': offset})}"


def fetch_page(url: str, timeout: int = 30) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
            "Cache-Control": "no-cache",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        content = response.read()
        encoding = response.headers.get_content_charset() or "utf-8"
    return content.decode(encoding, errors="replace")


def has_access_challenge(html: str) -> bool:
    normalized = html.casefold()
    return any(marker.casefold() in normalized for marker in ACCESS_MARKERS)


def has_login_page(html: str) -> bool:
    normalized = html.casefold()
    return any(marker.casefold() in normalized for marker in LOGIN_MARKERS)


def extract_total_count(html: str) -> int | None:
    match = re.search(r"([0-9][0-9\.\s]*)\s+ilan\s+bulundu", html, flags=re.IGNORECASE)
    if not match:
        return None
    digits = re.sub(r"\D", "", match.group(1))
    return int(digits) if digits else None


def scrape_page(offset: int, page_size: int, db_path: str) -> PageResult:
    url = build_url(offset, page_size)
    html = fetch_page(url)

    if has_access_challenge(html):
        debug_path = DEFAULT_DEBUG_PATH
        debug_path.parent.mkdir(parents=True, exist_ok=True)
        debug_path.write_text(html, encoding="utf-8")
        raise RuntimeError(f"Access challenge detected. Saved HTML to {debug_path}.")

    listings = parse_search_results(html)
    if not listings:
        debug_path = DEFAULT_DEBUG_PATH
        debug_path.parent.mkdir(parents=True, exist_ok=True)
        debug_path.write_text(html, encoding="utf-8")
        raise RuntimeError(f"No listings parsed at offset={offset}. Saved HTML to {debug_path}.")

    with ListingStore(db_path) as store:
        previous_total = store.count()
        store.upsert_many(listings)
        stored_total = store.count()
        changed = stored_total - previous_total

    return PageResult(offset=offset, parsed=len(listings), changed=changed, stored_total=stored_total)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scrape Sahibinden automobile category pages into SQLite.")
    parser.add_argument("--mode", choices=["browser", "http"], default="browser")
    parser.add_argument("--page-size", type=int, default=50, choices=[20, 50])
    parser.add_argument("--start-offset", type=int, default=None)
    parser.add_argument("--max-pages", type=int, default=20)
    parser.add_argument("--delay-min", type=float, default=1.0)
    parser.add_argument("--delay-max", type=float, default=2.5)
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--checkpoint-path", default=str(DEFAULT_CHECKPOINT_PATH))
    parser.add_argument("--manual-wait-seconds", type=float, default=45)
    parser.add_argument("--reset-checkpoint", action="store_true")
    return parser


def store_html_page(
    html: str,
    offset: int,
    page_size: int,
    db_path: str,
    city_override: str | None = None,
    district_override: str | None = None,
    brand_override: str | None = None,
    series_override: str | None = None,
) -> PageResult:
    listings = parse_search_results(html)
    if not listings:
        DEFAULT_DEBUG_PATH.parent.mkdir(parents=True, exist_ok=True)
        DEFAULT_DEBUG_PATH.write_text(html, encoding="utf-8")
        if has_access_challenge(html):
            raise RuntimeError(f"Access challenge detected. Saved HTML to {DEFAULT_DEBUG_PATH}.")
        raise RuntimeError(f"No listings parsed at offset={offset}. Saved HTML to {DEFAULT_DEBUG_PATH}.")

    if city_override:
        for listing in listings:
            if listing.city and listing.city.casefold() != city_override.casefold() and not listing.district:
                listing.district = listing.city
            listing.city = city_override
            if district_override and not listing.district:
                listing.district = district_override

    if brand_override:
        def option_key(value: str | None) -> str:
            return re.sub(
                r"[^a-z0-9]+",
                "",
                unicodedata.normalize("NFKD", (value or "").casefold())
                .encode("ascii", "ignore")
                .decode("ascii"),
            )

        override_key = option_key(brand_override)
        series_key = option_key(series_override)
        for listing in listings:
            raw_brand = listing.brand
            raw_series = listing.series
            raw_model = listing.model
            raw_engine = listing.engine
            listing_key = option_key(raw_brand)

            if series_override:
                if listing_key == override_key:
                    if raw_series and option_key(raw_series) != series_key:
                        # A series-filtered page retained the brand but omitted the series tag.
                        listing.model = raw_series
                        listing.engine = raw_model or raw_engine
                elif listing_key == series_key:
                    # The page omitted only the brand tag.
                    listing.model = raw_series
                    listing.engine = raw_model or raw_engine
                else:
                    # The page omitted both brand and series tags.
                    listing.model = raw_brand
                    listing.engine = raw_series or raw_model or raw_engine
                listing.series = series_override
            elif raw_brand and listing_key != override_key:
                # Brand-filtered result pages omit the brand tag, shifting the remaining tags left.
                listing.engine = raw_model or raw_engine
                listing.model = raw_series
                listing.series = raw_brand
            listing.brand = brand_override

    with ListingStore(db_path) as store:
        previous_total = store.count()
        store.upsert_many(listings)
        stored_total = store.count()
        changed = stored_total - previous_total
    return PageResult(offset=offset, parsed=len(listings), changed=changed, stored_total=stored_total)


async def run_browser_mode(args: argparse.Namespace, offset: int, checkpoint_path: Path) -> None:
    config = ScraperConfig(
        query="Otomobil",
        max_pages=1,
        delay_min=args.delay_min,
        delay_max=args.delay_max,
        db_path=args.db_path,
        headless=False,
        browser_executable_path=find_browser_executable(),
        user_data_dir=str(SCRAPER_PROFILE_PATH),
        sandbox=False,
        manual_wait_seconds=args.manual_wait_seconds,
    )
    driver = await start_browser(config)
    try:
        total_count = None
        print(f"Starting category browser scrape. offset={offset} page_size={args.page_size}", flush=True)
        for page_index in range(1, args.max_pages + 1):
            url = build_url(offset, args.page_size)
            print(f"Opening {url}", flush=True)
            tab = await driver.get(url)
            await wait_for_manual_access_check(tab, config, f"opening offset {offset}")
            html = await tab.get_content()
            if total_count is None:
                total_count = extract_total_count(html)
                print(f"reported_total_count={total_count}", flush=True)

            try:
                result = store_html_page(html, offset, args.page_size, args.db_path)
            except RuntimeError as exc:
                print(f"STOP offset={offset} error={exc}", flush=True)
                break

            next_offset = offset + args.page_size
            save_checkpoint(checkpoint_path, next_offset)
            print(
                f"page={page_index} offset={result.offset} parsed={result.parsed} "
                f"changed={result.changed} stored_total={result.stored_total} next_offset={next_offset}",
                flush=True,
            )
            offset = next_offset

            if total_count is not None and offset >= total_count:
                print("Reached reported total count.", flush=True)
                break
            if page_index < args.max_pages:
                time.sleep(random.uniform(args.delay_min, args.delay_max))
    finally:
        driver.stop()


def run_http_mode(args: argparse.Namespace, offset: int, checkpoint_path: Path) -> None:
    first_html = fetch_page(build_url(offset, args.page_size))
    total_count = extract_total_count(first_html)
    print(f"Starting category scrape. offset={offset} page_size={args.page_size} total_count={total_count}", flush=True)

    for page_index in range(1, args.max_pages + 1):
        try:
            if page_index == 1:
                html = first_html
                result = store_html_page(html, offset, args.page_size, args.db_path)
            else:
                result = scrape_page(offset, args.page_size, args.db_path)
        except (HTTPError, URLError, TimeoutError, RuntimeError) as exc:
            print(f"STOP offset={offset} error={type(exc).__name__}: {exc}", flush=True)
            break

        next_offset = offset + args.page_size
        save_checkpoint(checkpoint_path, next_offset)
        print(
            f"page={page_index} offset={result.offset} parsed={result.parsed} "
            f"changed={result.changed} stored_total={result.stored_total} next_offset={next_offset}",
            flush=True,
        )
        offset = next_offset

        if total_count is not None and offset >= total_count:
            print("Reached reported total count.", flush=True)
            break
        if page_index < args.max_pages:
            time.sleep(random.uniform(args.delay_min, args.delay_max))


def main() -> None:
    args = build_parser().parse_args()
    checkpoint_path = Path(args.checkpoint_path)
    if args.reset_checkpoint and checkpoint_path.exists():
        checkpoint_path.unlink()

    offset = args.start_offset if args.start_offset is not None else load_checkpoint(checkpoint_path)
    if args.mode == "browser":
        asyncio.run(run_browser_mode(args, offset, checkpoint_path))
    else:
        run_http_mode(args, offset, checkpoint_path)


if __name__ == "__main__":
    main()
