"""Scrape newest Sahibinden automobile listings until a date cutoff."""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from src.experimental.sahibinden.category_page_scraper import (
    BASE_URL,
    DEFAULT_DEBUG_PATH,
    extract_total_count,
    find_browser_executable,
    has_access_challenge,
    has_login_page,
)
from src.experimental.sahibinden.scraper import (
    ScraperConfig,
    parse_search_results,
    start_browser,
    wait_for_manual_access_check,
)
from src.ingestion.schema import VehicleListing
from src.ingestion.storage import DEFAULT_DB_PATH, ListingStore

CHECKPOINT_PATH = Path("data") / "runtime" / "recent_listing_checkpoint.json"
SCRAPER_PROFILE_PATH = Path("data") / "runtime" / "edge-profile-city"

DEFAULT_PRICE_BANDS = (
    (0, 100_000),
    (100_001, 200_000),
    (200_001, 300_000),
    (300_001, 400_000),
    (400_001, 500_000),
    (500_001, 600_000),
    (600_001, 700_000),
    (700_001, 800_000),
    (800_001, 900_000),
    (900_001, 1_000_000),
    (1_000_001, 1_100_000),
    (1_100_001, 1_200_000),
    (1_200_001, 1_300_000),
    (1_300_001, 1_400_000),
    (1_400_001, 1_500_000),
    (1_500_001, 1_600_000),
    (1_600_001, 1_700_000),
    (1_700_001, 1_800_000),
    (1_800_001, 1_900_000),
    (1_900_001, 2_000_000),
    (2_000_001, 2_250_000),
    (2_250_001, 2_500_000),
    (2_500_001, 2_750_000),
    (2_750_001, 3_000_000),
    (3_000_001, 3_250_000),
    (3_250_001, 3_500_000),
    (3_500_001, 3_750_000),
    (3_750_001, 4_000_000),
    (4_000_001, 4_250_000),
    (4_250_001, 4_500_000),
    (4_500_001, 4_750_000),
    (4_750_001, 5_000_000),
    (5_000_001, 6_000_000),
    (6_000_001, 7_500_000),
    (7_500_001, 10_000_000),
    (10_000_001, 15_000_000),
    (15_000_001, None),
)

TURKISH_MONTHS = {
    "ocak": 1,
    "subat": 2,
    "şubat": 2,
    "mart": 3,
    "nisan": 4,
    "mayis": 5,
    "mayıs": 5,
    "haziran": 6,
    "temmuz": 7,
    "agustos": 8,
    "ağustos": 8,
    "eylul": 9,
    "eylül": 9,
    "ekim": 10,
    "kasim": 11,
    "kasım": 11,
    "aralik": 12,
    "aralık": 12,
}


@dataclass(slots=True)
class PageResult:
    offset: int
    parsed: int
    recent: int
    old: int
    unknown_date: int
    added: int
    upserted: int
    stored_total: int
    signature: str


@dataclass(frozen=True, slots=True)
class PriceBand:
    price_min: int | None
    price_max: int | None

    @property
    def key(self) -> str:
        min_part = str(self.price_min) if self.price_min is not None else "0"
        max_part = str(self.price_max) if self.price_max is not None else "plus"
        return f"{min_part}-{max_part}"

    @property
    def label(self) -> str:
        if self.price_max is None:
            return f"{self.price_min}+"
        return f"{self.price_min}-{self.price_max}"


class FilterSegment(ABC):
    """A polymorphic search segment that can label listings it captures."""

    name: str
    query_params: dict[str, str]

    @property
    def key(self) -> str:
        params = "&".join(f"{key}={value}" for key, value in sorted(self.query_params.items()))
        return f"{self.name}:{params}"

    @abstractmethod
    def apply_labels(self, listing: VehicleListing) -> None:
        """Attach segment-specific labels to a parsed listing."""


class GeneralRecentSegment(FilterSegment):
    name = "general_24h"
    query_params = {"date": "1day"}

    def apply_labels(self, listing: VehicleListing) -> None:
        listing.scrape_segment = self.name


class CleanClaimedRecentSegment(FilterSegment):
    name = "clean_24h"
    query_params = {
        "date": "1day",
        "unpaintedParts": "true",
        "unchangingTracks": "true",
    }

    def apply_labels(self, listing: VehicleListing) -> None:
        listing.paint_status = "Boyasız"
        listing.changed_part_status = "Değişensiz"
        listing.damage_status = "clean_claimed"
        listing.is_clean_claimed = 1
        listing.scrape_segment = self.name


def normalize_text(value: str) -> str:
    normalized = value.casefold().strip()
    normalized = normalized.replace("ı", "i").replace("ğ", "g").replace("ü", "u").replace("ş", "s")
    normalized = normalized.replace("ö", "o").replace("ç", "c")
    return re.sub(r"\s+", " ", normalized)


def parse_listing_date(value: str | None, today: date) -> date | None:
    if not value:
        return None

    normalized = normalize_text(value)
    if "bugun" in normalized:
        return today
    if "dun" in normalized:
        return today - timedelta(days=1)

    compact = re.sub(r"\s+", " ", value.casefold().strip())
    match = re.search(r"(\d{1,2})\s+([a-zçğıöşü]+)\s+(\d{4})", compact, flags=re.IGNORECASE)
    if not match:
        return None

    day = int(match.group(1))
    month_name = match.group(2)
    year = int(match.group(3))
    month = TURKISH_MONTHS.get(month_name) or TURKISH_MONTHS.get(normalize_text(month_name))
    if not month:
        return None
    try:
        return date(year, month, day)
    except ValueError:
        return None


def parse_price_bands(value: str | None) -> list[PriceBand]:
    raw_bands = value or ",".join(
        f"{price_min}-{price_max}" if price_max is not None else f"{price_min}+"
        for price_min, price_max in DEFAULT_PRICE_BANDS
    )
    bands: list[PriceBand] = []
    for raw_band in raw_bands.split(","):
        band = raw_band.strip()
        if not band:
            continue
        if band.endswith("+"):
            bands.append(PriceBand(price_min=int(band[:-1]), price_max=None))
            continue
        try:
            price_min_raw, price_max_raw = band.split("-", 1)
            bands.append(PriceBand(price_min=int(price_min_raw), price_max=int(price_max_raw)))
        except ValueError as exc:
            raise SystemExit(f"Invalid price band: {band}. Expected 0-300000 or 5000000+ format.") from exc
    if not bands:
        raise SystemExit("No valid price bands were provided.")
    return bands


def load_checkpoint(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"segment_index": 0, "band_index": 0, "offset": 0, "completed": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    if "segment_index" not in data:
        data["segment_index"] = 0
    if "band_index" not in data:
        data["band_index"] = 0
    if "completed" not in data:
        data["completed"] = []
    return data


def price_bands_signature(price_bands: list[PriceBand]) -> str:
    return ",".join(price_band.key for price_band in price_bands)


def filter_segments_signature(filter_segments: list[FilterSegment]) -> str:
    return ",".join(filter_segment.key for filter_segment in filter_segments)


def parse_filter_segments(value: str | None) -> list[FilterSegment]:
    selected = [item.strip() for item in (value or "clean,general").split(",") if item.strip()]
    known = {
        "clean": CleanClaimedRecentSegment,
        "general": GeneralRecentSegment,
    }
    segments: list[FilterSegment] = []
    for item in selected:
        if item not in known:
            raise SystemExit(f"Invalid filter segment: {item}. Expected clean,general.")
        segments.append(known[item]())
    if not segments:
        raise SystemExit("No filter segments were provided.")
    return segments


def save_checkpoint(
    path: Path,
    *,
    segment_index: int,
    band_index: int,
    offset: int,
    completed: list[str],
    days: int,
    price_bands_key: str,
    filter_segments_key: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "days": days,
        "price_bands_key": price_bands_key,
        "filter_segments_key": filter_segments_key,
        "segment_index": segment_index,
        "band_index": band_index,
        "offset": offset,
        "completed": completed,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


class CheckpointManager:
    """Load, validate, and persist scraper progress."""

    def __init__(self, path: Path, *, days: int, price_bands_key: str, filter_segments_key: str) -> None:
        self.path = path
        self.days = days
        self.price_bands_key = price_bands_key
        self.filter_segments_key = filter_segments_key

    def reset(self) -> None:
        if self.path.exists():
            self.path.unlink()

    def load(self) -> dict[str, object]:
        checkpoint = load_checkpoint(self.path)
        if not self.path.exists():
            return checkpoint

        if (
            checkpoint.get("days") != self.days
            or checkpoint.get("price_bands_key") != self.price_bands_key
            or checkpoint.get("filter_segments_key") != self.filter_segments_key
        ):
            print("Checkpoint context changed; starting recent scraper from the first price band.", flush=True)
            return {"segment_index": 0, "band_index": 0, "offset": 0, "completed": []}
        return checkpoint

    def save(self, *, segment_index: int, band_index: int, offset: int, completed: list[str]) -> None:
        save_checkpoint(
            self.path,
            segment_index=segment_index,
            band_index=band_index,
            offset=offset,
            completed=completed,
            days=self.days,
            price_bands_key=self.price_bands_key,
            filter_segments_key=self.filter_segments_key,
        )


def build_url(
    offset: int,
    page_size: int,
    price_band: PriceBand | None = None,
    filter_segment: FilterSegment | None = None,
) -> str:
    parsed = urlparse(BASE_URL)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.update(
        {
            "sorting": "date_desc",
            "pagingSize": str(page_size),
            "pagingOffset": str(offset),
        }
    )
    if price_band:
        if price_band.price_min is not None:
            query["price_min"] = str(price_band.price_min)
        if price_band.price_max is not None:
            query["price_max"] = str(price_band.price_max)
    if filter_segment:
        query.update(filter_segment.query_params)
    return urlunparse(parsed._replace(query=urlencode(query)))


def split_recent_listings(listings: list[VehicleListing], cutoff: date, today: date) -> tuple[list[VehicleListing], int, int]:
    recent: list[VehicleListing] = []
    old = 0
    unknown = 0
    for listing in listings:
        parsed_date = parse_listing_date(listing.listing_date, today)
        if parsed_date is None:
            unknown += 1
            recent.append(listing)
        elif parsed_date >= cutoff:
            recent.append(listing)
        else:
            old += 1
    return recent, old, unknown


async def wait_for_manual_login(tab: object, config: ScraperConfig, context: str) -> str:
    html = await tab.get_content()
    if config.manual_wait_seconds <= 0 or not has_login_page(html):
        return html

    print(
        f"Login page detected after {context}. "
        "Please sign in from the visible Sahibinden browser window.",
        flush=True,
    )
    deadline = asyncio.get_running_loop().time() + config.manual_wait_seconds
    while asyncio.get_running_loop().time() < deadline:
        await asyncio.sleep(2)
        html = await tab.get_content()
        if not has_login_page(html):
            print("Login page cleared; continuing.", flush=True)
            time.sleep(random.uniform(config.delay_min, config.delay_max))
            return html

    print("Login page is still visible; keeping current page state.", flush=True)
    return html


def store_recent_page(
    html: str,
    offset: int,
    db_path: str,
    cutoff: date,
    today: date,
    filter_segment: FilterSegment,
) -> PageResult:
    listings = parse_search_results(html)
    if not listings:
        DEFAULT_DEBUG_PATH.parent.mkdir(parents=True, exist_ok=True)
        DEFAULT_DEBUG_PATH.write_text(html, encoding="utf-8")
        if has_access_challenge(html):
            raise RuntimeError(f"Access challenge detected. Saved HTML to {DEFAULT_DEBUG_PATH}.")
        raise RuntimeError(f"No listings parsed at offset={offset}. Saved HTML to {DEFAULT_DEBUG_PATH}.")

    recent_listings, old, unknown = split_recent_listings(listings, cutoff, today)
    for listing in recent_listings:
        filter_segment.apply_labels(listing)
    signature = ",".join(
        str(listing.source_listing_id or listing.listing_url or listing.title)
        for listing in listings[: min(10, len(listings))]
    )
    with ListingStore(db_path) as store:
        previous_total = store.count()
        upserted = store.upsert_many(recent_listings)
        stored_total = store.count()

    return PageResult(
        offset=offset,
        parsed=len(listings),
        recent=len(recent_listings),
        old=old,
        unknown_date=unknown,
        added=max(0, stored_total - previous_total),
        upserted=upserted,
        stored_total=stored_total,
        signature=signature,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scrape newest automobile listings mixed across cities.")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--page-size", type=int, default=50, choices=[20, 50])
    parser.add_argument("--max-pages", type=int, default=0, help="Use 0 to keep going until old-listing stop condition.")
    parser.add_argument("--start-offset", type=int, default=None)
    parser.add_argument("--price-bands", default=None, help="Comma-separated bands, e.g. 0-300000,300001-600000,5000000+")
    parser.add_argument(
        "--filter-segments",
        default="clean,general",
        help="Comma-separated segment names. Options: clean,general. clean means son 24 saat + boyasız + değişensiz.",
    )
    parser.add_argument("--delay-min", type=float, default=3.0)
    parser.add_argument("--delay-max", type=float, default=7.0)
    parser.add_argument("--manual-wait-seconds", type=float, default=120)
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--checkpoint-path", default=str(CHECKPOINT_PATH))
    parser.add_argument("--reset-checkpoint", action="store_true")
    parser.add_argument("--max-old-pages", type=int, default=3)
    parser.add_argument("--max-stale-pages", type=int, default=10)
    parser.add_argument("--max-repeated-pages", type=int, default=2, help="Use 0 to disable repeated-page stopping.")
    parser.add_argument("--stop-on-access", action="store_true")
    return parser


class RecentListingScraper:
    """Coordinate recent listing scraping across segments and price bands."""

    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args

    async def run(self) -> None:
        await run_recent_listings(self.args)


async def run_recent_listings(args: argparse.Namespace) -> None:
    checkpoint_path = Path(args.checkpoint_path)
    price_bands = parse_price_bands(args.price_bands)
    price_bands_key = price_bands_signature(price_bands)
    filter_segments = parse_filter_segments(args.filter_segments)
    filter_segments_key = filter_segments_signature(filter_segments)
    checkpoint_manager = CheckpointManager(
        checkpoint_path,
        days=args.days,
        price_bands_key=price_bands_key,
        filter_segments_key=filter_segments_key,
    )
    if args.reset_checkpoint:
        checkpoint_manager.reset()

    checkpoint = checkpoint_manager.load()

    completed = [str(item) for item in checkpoint.get("completed", [])]
    segment_index = int(checkpoint.get("segment_index", 0))
    band_index = int(checkpoint.get("band_index", 0))
    offset = args.start_offset if args.start_offset is not None else int(checkpoint.get("offset", 0))
    today = date.today()
    cutoff = today - timedelta(days=args.days)

    config = ScraperConfig(
        query="Otomobil",
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
        max_pages = args.max_pages if args.max_pages > 0 else 1_000_000
        pending_segments = filter_segments[segment_index:]
        print(
            f"Starting recent listings scrape. days={args.days} cutoff={cutoff.isoformat()} "
            f"segment_index={segment_index} band_index={band_index} offset={offset} "
            f"page_size={args.page_size} segments_remaining={len(pending_segments)}",
            flush=True,
        )

        for relative_segment_index, filter_segment in enumerate(pending_segments):
            absolute_segment_index = segment_index + relative_segment_index
            segment_band_start = band_index if relative_segment_index == 0 else 0
            pending_bands = price_bands[segment_band_start:]
            print(f"\nRecent filter segment {absolute_segment_index + 1}: {filter_segment.name}", flush=True)

            for relative_band_index, price_band in enumerate(pending_bands):
                absolute_band_index = segment_band_start + relative_band_index
                completed_key = f"{filter_segment.key}|{price_band.key}"
                if completed_key in completed:
                    continue

                current_offset = offset if relative_segment_index == 0 and relative_band_index == 0 else 0
                total_count = None
                old_pages = 0
                stale_pages = 0
                repeated_pages = 0
                previous_signature = None
                print(f"\nRecent price band {absolute_band_index + 1}: {price_band.label}", flush=True)

                for page_index in range(1, max_pages + 1):
                    url = build_url(current_offset, args.page_size, price_band, filter_segment)
                    print(f"Opening {url}", flush=True)
                    tab = await driver.get(url)
                    await wait_for_manual_access_check(
                        tab,
                        config,
                        f"opening recent {filter_segment.name} {price_band.key} offset {current_offset}",
                    )
                    html = await wait_for_manual_login(
                        tab,
                        config,
                        f"opening recent {filter_segment.name} {price_band.key} offset {current_offset}",
                    )
                    if total_count is None:
                        total_count = extract_total_count(html)
                        print(f"reported_total_count={total_count}", flush=True)

                    try:
                        result = store_recent_page(html, current_offset, args.db_path, cutoff, today, filter_segment)
                    except RuntimeError as exc:
                        print(
                            f"EMPTY/STOP recent segment={filter_segment.name} band={price_band.key} "
                            f"offset={current_offset} error={exc}",
                            flush=True,
                        )
                        if "No listings parsed" in str(exc) and not (has_login_page(html) or has_access_challenge(html)):
                            print("No more listings were returned for this price band; moving to the next band.", flush=True)
                            break
                        checkpoint_manager.save(
                            segment_index=absolute_segment_index,
                            band_index=absolute_band_index,
                            offset=current_offset,
                            completed=completed,
                        )
                        if has_login_page(html) or has_access_challenge(html):
                            print("Access/login page detected for recent scraper; keeping current offset.", flush=True)
                            if args.stop_on_access:
                                return
                        print("Current price band was not marked complete; rerun without reset to continue safely.", flush=True)
                        return

                    next_offset = current_offset + args.page_size
                    checkpoint_manager.save(
                        segment_index=absolute_segment_index,
                        band_index=absolute_band_index,
                        offset=next_offset,
                        completed=completed,
                    )
                    print(
                        f"recent segment={filter_segment.name} band={price_band.label} page={page_index} "
                        f"offset={result.offset} parsed={result.parsed} recent={result.recent} old={result.old} "
                        f"unknown_date={result.unknown_date} added={result.added} upserted={result.upserted} "
                        f"stored_total={result.stored_total} next_offset={next_offset} total_count={total_count}",
                        flush=True,
                    )
                    current_offset = next_offset

                    if previous_signature and result.signature == previous_signature:
                        repeated_pages += 1
                        print(f"Repeated page signature detected ({repeated_pages}); moving within current band.", flush=True)
                        if args.max_repeated_pages > 0 and repeated_pages >= args.max_repeated_pages:
                            print(f"Repeated-page limit reached for {price_band.label}; moving to next price band.", flush=True)
                            break
                    else:
                        repeated_pages = 0
                    previous_signature = result.signature

                    if args.max_old_pages > 0 and result.old >= result.parsed - result.unknown_date:
                        old_pages += 1
                        if old_pages >= args.max_old_pages:
                            print(f"Old-listing page limit reached for {price_band.label}; moving to next band.", flush=True)
                            break
                    else:
                        old_pages = 0

                    if result.added == 0:
                        stale_pages += 1
                        if args.max_stale_pages > 0 and stale_pages >= args.max_stale_pages:
                            print(f"No new listings for {stale_pages} consecutive pages; moving to next band.", flush=True)
                            break
                    else:
                        stale_pages = 0

                    if total_count is not None and current_offset >= total_count:
                        break
                    if page_index < max_pages:
                        time.sleep(random.uniform(args.delay_min, args.delay_max))

                if completed_key not in completed:
                    completed.append(completed_key)
                checkpoint_manager.save(
                    segment_index=absolute_segment_index,
                    band_index=absolute_band_index + 1,
                    offset=0,
                    completed=completed,
                )

            checkpoint_manager.save(
                segment_index=absolute_segment_index + 1,
                band_index=0,
                offset=0,
                completed=completed,
            )
    finally:
        driver.stop()


def main() -> None:
    args = build_parser().parse_args()
    asyncio.run(run(args))


async def run(args: argparse.Namespace) -> None:
    await RecentListingScraper(args).run()


if __name__ == "__main__":
    main()
