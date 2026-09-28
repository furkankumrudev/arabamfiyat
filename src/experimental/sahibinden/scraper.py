"""Sahibinden search-result ingestion prototype.

This module collects listing rows from Sahibinden search result pages and writes
normalized records into SQLite. Use it conservatively for bootcamp research and
respect the source site's rules, robots controls, and rate limits.
"""

from __future__ import annotations

import argparse
import asyncio
import random
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from src.ingestion.schema import VehicleListing
from src.ingestion.storage import DEFAULT_DB_PATH, ListingStore

BASE_URL = "https://www.sahibinden.com"
DEFAULT_DEBUG_HTML_PATH = Path("data") / "runtime" / "debug_sahibinden_home.html"
DEFAULT_DEBUG_RESULTS_PATH = Path("data") / "runtime" / "debug_sahibinden_results.html"
ACCESS_CHALLENGE_MARKERS = (
    "bağlantınız kontrol ediliyor",
    "baglantiniz kontrol ediliyor",
    "basılı tut",
    "basili tut",
    "olağan dışı erişim",
    "olagan disi erisim",
    "cdn-cgi/challenge-platform",
)

TURKISH_CITY_NAMES = {
    "Adana",
    "Adıyaman",
    "Afyonkarahisar",
    "Ağrı",
    "Aksaray",
    "Amasya",
    "Ankara",
    "Antalya",
    "Ardahan",
    "Artvin",
    "Aydın",
    "Balıkesir",
    "Bartın",
    "Batman",
    "Bayburt",
    "Bilecik",
    "Bingöl",
    "Bitlis",
    "Bolu",
    "Burdur",
    "Bursa",
    "Çanakkale",
    "Çankırı",
    "Çorum",
    "Denizli",
    "Diyarbakır",
    "Düzce",
    "Edirne",
    "Elazığ",
    "Erzincan",
    "Erzurum",
    "Eskişehir",
    "Gaziantep",
    "Giresun",
    "Gümüşhane",
    "Hakkari",
    "Hatay",
    "Iğdır",
    "Isparta",
    "İstanbul",
    "İzmir",
    "Kahramanmaraş",
    "Karabük",
    "Karaman",
    "Kars",
    "Kastamonu",
    "Kayseri",
    "Kırıkkale",
    "Kırklareli",
    "Kırşehir",
    "Kilis",
    "Kocaeli",
    "Konya",
    "Kütahya",
    "Malatya",
    "Manisa",
    "Mardin",
    "Mersin",
    "Muğla",
    "Muş",
    "Nevşehir",
    "Niğde",
    "Ordu",
    "Osmaniye",
    "Rize",
    "Sakarya",
    "Samsun",
    "Siirt",
    "Sinop",
    "Sivas",
    "Şanlıurfa",
    "Şırnak",
    "Tekirdağ",
    "Tokat",
    "Trabzon",
    "Tunceli",
    "Uşak",
    "Van",
    "Yalova",
    "Yozgat",
    "Zonguldak",
}


@dataclass(slots=True)
class ScraperConfig:
    query: str
    year_min: str | None = None
    year_max: str | None = None
    engine_volume: str | None = None
    transmission: str | None = None
    max_pages: int = 1
    delay_min: float = 2.5
    delay_max: float = 5.0
    db_path: str = str(DEFAULT_DB_PATH)
    headless: bool = False
    browser_executable_path: str | None = None
    user_data_dir: str | None = None
    sandbox: bool = True
    manual_wait_seconds: float = 0
    debug_html_path: str = str(DEFAULT_DEBUG_HTML_PATH)
    debug_results_path: str = str(DEFAULT_DEBUG_RESULTS_PATH)


def clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = re.sub(r"\s+", " ", value).strip()
    return normalized or None


def parse_int(value: str | None) -> int | None:
    if not value:
        return None
    digits = re.sub(r"[^0-9]", "", value)
    return int(digits) if digits else None


def infer_year_from_title(title: str) -> int | None:
    match = re.search(r"\b(19[5-9][0-9]|20[0-2][0-9])\b", title)
    if match:
        return int(match.group(1))

    short_match = re.search(r"\b([0-2][0-9])\s*(?:model|mdl)\b", title, flags=re.IGNORECASE)
    if short_match:
        year = int(short_match.group(1))
        return 2000 + year if year <= 29 else 1900 + year
    return None


def infer_mileage_from_title(title: str) -> int | None:
    normalized = (
        title.lower()
        .replace(".", "")
        .replace(",", "")
        .replace("ooo", "000")
        .replace("bin", "000")
    )
    match = re.search(r"\b([0-9]{2,6})\s*(?:km|kilometre|kmde|binde)\b", normalized)
    if match:
        return int(match.group(1))

    binde_match = re.search(r"\b([0-9]{2,3})\s*000de\b", normalized)
    if binde_match:
        return int(binde_match.group(1)) * 1000
    return None


def apply_query_defaults(listings: list[VehicleListing], query: str) -> list[VehicleListing]:
    parts = query.split()
    brand = parts[0] if parts else None
    series = " ".join(parts[1:]) if len(parts) > 1 else None
    for listing in listings:
        if brand:
            listing.brand = brand
        if series:
            listing.series = series
    return listings


def split_location(value: str | None) -> tuple[str | None, str | None]:
    if not value:
        return None, None
    parts = [part for part in re.split(r"\s*/\s*|\s{2,}", value.strip()) if part]
    if len(parts) >= 2:
        return parts[0], parts[1]
    compact_value = parts[0] if parts else value.strip()
    for city in sorted(TURKISH_CITY_NAMES, key=len, reverse=True):
        if compact_value.casefold() == city.casefold():
            return city, None
        prefix = f"{city} "
        if compact_value.casefold().startswith(prefix.casefold()):
            district = compact_value[len(prefix) :].strip() or None
            return city, district
    return compact_value, None


def extract_listing(row: Tag) -> VehicleListing | None:
    source_listing_id = row.get("data-id")

    title_tag = row.select_one("td.searchResultsTitleValue a.classifiedTitle")
    title = clean_text(title_tag.get_text(" ") if title_tag else None)
    if not title:
        return None

    listing_url = None
    if title_tag and title_tag.get("href"):
        listing_url = urljoin(BASE_URL, str(title_tag.get("href")))

    tag_values = [clean_text(tag.get_text(" ")) for tag in row.select("td.searchResultsTagAttributeValue")]
    brand = tag_values[0] if len(tag_values) > 0 else None
    series = tag_values[1] if len(tag_values) > 1 else None
    model = tag_values[2] if len(tag_values) > 2 else None
    engine = tag_values[3] if len(tag_values) > 3 else None

    attr_values = [clean_text(tag.get_text(" ")) for tag in row.select("td.searchResultsAttributeValue")]
    year = parse_int(attr_values[0] if len(attr_values) > 0 else None) or infer_year_from_title(title)
    mileage_km = parse_int(attr_values[1] if len(attr_values) > 1 else None) or infer_mileage_from_title(title)
    color = attr_values[2] if len(attr_values) > 2 else None

    price_tag = row.select_one("td.searchResultsPriceValue div.classified-price-container span")
    price = parse_int(price_tag.get_text(" ") if price_tag else None)

    date_tag = row.select_one("td.searchResultsDateValue")
    listing_date = clean_text(date_tag.get_text(" ") if date_tag else None)

    location_tag = row.select_one("td.searchResultsLocationValue")
    city, district = split_location(clean_text(location_tag.get_text(" ") if location_tag else None))

    image_tag = row.select_one("td.searchResultsLargeThumbnail img")
    image_url = None
    if image_tag:
        image_url = image_tag.get("data-src") or image_tag.get("src")

    return VehicleListing.create(
        source="sahibinden",
        source_listing_id=str(source_listing_id) if source_listing_id else None,
        title=title,
        brand=brand,
        series=series,
        model=model,
        year=year,
        mileage_km=mileage_km,
        transmission=None,
        fuel_type=None,
        body_type=None,
        color=color,
        engine=engine,
        city=city,
        district=district,
        seller_type=None,
        price=price,
        listing_date=listing_date,
        listing_url=listing_url,
        image_url=str(image_url) if image_url else None,
    )


def parse_search_results(html: str) -> list[VehicleListing]:
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.select("tr.searchResultsItem[data-id]")
    listings = []
    for row in rows:
        listing = extract_listing(row)
        if listing:
            listings.append(listing)
    return listings


async def polite_sleep(config: ScraperConfig) -> None:
    await asyncio.sleep(random.uniform(config.delay_min, config.delay_max))


async def select_with_timeout(tab: object, selector: str, timeout: float = 10) -> object | None:
    try:
        return await asyncio.wait_for(tab.select(selector), timeout=timeout)
    except (Exception, TimeoutError):
        return None


async def write_debug_html(tab: object, path: str) -> None:
    debug_path = Path(path)
    debug_path.parent.mkdir(parents=True, exist_ok=True)
    html = await tab.get_content()
    debug_path.write_text(html, encoding="utf-8")


async def page_has_access_challenge(tab: object) -> bool:
    html = (await tab.get_content()).casefold()
    return any(marker.casefold() in html for marker in ACCESS_CHALLENGE_MARKERS)


async def wait_for_manual_access_check(tab: object, config: ScraperConfig, context: str) -> None:
    if config.manual_wait_seconds <= 0 or not await page_has_access_challenge(tab):
        return

    print(
        f"Access check detected after {context}. "
        "Please complete the visible Sahibinden 'Basılı Tut' check in the browser window.",
        flush=True,
    )
    deadline = asyncio.get_running_loop().time() + config.manual_wait_seconds
    while asyncio.get_running_loop().time() < deadline:
        await asyncio.sleep(2)
        if not await page_has_access_challenge(tab):
            print("Access check completed; continuing.", flush=True)
            await polite_sleep(config)
            return

    print("Access check is still visible; continuing with the current page state.", flush=True)


async def click_if_exists(tab: object, selector: str) -> bool:
    element = await select_with_timeout(tab, selector, timeout=5)
    if not element:
        return False
    await element.click()
    return True


async def apply_filters(tab: object, config: ScraperConfig) -> None:
    if config.year_min:
        element = await select_with_timeout(tab, 'input[name="a5_min"]', timeout=5)
        if element:
            await element.send_keys(config.year_min)
    if config.year_max:
        element = await select_with_timeout(tab, 'input[name="a5_max"]', timeout=5)
        if element:
            await element.send_keys(config.year_max)

    if config.transmission:
        transmission = config.transmission.lower().strip().replace("\u00fc", "u")
        selector = None
        if transmission in {"manuel", "manual", "duz"}:
            selector = 'a[data-value="32467"].js-attribute.facetedCheckbox'
        elif transmission in {"otomatik", "automatic"}:
            selector = 'a[data-value="32466"].js-attribute.facetedCheckbox'
        if selector:
            await click_if_exists(tab, selector)

    apply_button = await select_with_timeout(tab, "button.js-manual-search-button", timeout=5)
    if apply_button:
        await apply_button.click()


async def start_browser(config: ScraperConfig) -> object:
    import nodriver as uc

    user_data_dir = str(Path(config.user_data_dir).resolve()) if config.user_data_dir else None
    print("Starting browser...", flush=True)
    return await uc.start(
        headless=config.headless,
        browser_executable_path=config.browser_executable_path,
        user_data_dir=user_data_dir,
        sandbox=config.sandbox,
    )


async def scrape_with_driver(driver: object, config: ScraperConfig) -> int:
    saved_total = 0
    print(f"Opening {BASE_URL}...", flush=True)
    tab = await driver.get(BASE_URL)
    await polite_sleep(config)
    await wait_for_manual_access_check(tab, config, "opening home page")

    try:
        cookie_button = await asyncio.wait_for(tab.find("Kabul Et", best_match=True), timeout=5)
        if cookie_button:
            await cookie_button.click()
            await polite_sleep(config)
    except (Exception, TimeoutError):
        pass

    print("Looking for search input...", flush=True)
    search_box = await select_with_timeout(tab, "#searchText", timeout=10)
    if not search_box:
        await wait_for_manual_access_check(tab, config, "looking for search input")
        search_box = await select_with_timeout(tab, "#searchText", timeout=10)
    if not search_box:
        await write_debug_html(tab, config.debug_html_path)
        raise RuntimeError(
            "Search input could not be found. "
            f"Saved received HTML to {config.debug_html_path}."
        )
    await search_box.send_keys(config.query)
    await polite_sleep(config)

    search_button = await select_with_timeout(tab, 'button[type="submit"][value="Ara"]', timeout=10)
    if not search_button:
        raise RuntimeError("Search button could not be found.")
    await search_button.click()
    await polite_sleep(config)
    await wait_for_manual_access_check(tab, config, "submitting search")

    suggestion = await select_with_timeout(tab, "li.first-child.ui-menu-item a", timeout=5)
    if suggestion:
        await suggestion.click()
        await polite_sleep(config)
        await wait_for_manual_access_check(tab, config, "opening suggestion")

    category = await select_with_timeout(tab, "#searchCategoryContainer div div ul li:first-child a", timeout=5)
    if category:
        await category.click()
        await polite_sleep(config)
        await wait_for_manual_access_check(tab, config, "opening category")

    await click_if_exists(tab, 'a.paging-size.Limit50Passive[title="50"]')
    await apply_filters(tab, config)
    await polite_sleep(config)
    await wait_for_manual_access_check(tab, config, "applying filters")

    with ListingStore(config.db_path) as store:
        for page_number in range(1, config.max_pages + 1):
            await wait_for_manual_access_check(tab, config, f"reading page {page_number}")
            html = await tab.get_content()
            listings = apply_query_defaults(parse_search_results(html), config.query)
            if not listings:
                debug_path = Path(config.debug_results_path)
                debug_path.parent.mkdir(parents=True, exist_ok=True)
                debug_path.write_text(html, encoding="utf-8")
            saved_total += store.upsert_many(listings)
            print(f"page={page_number} parsed={len(listings)} stored_total={store.count()}", flush=True)

            if page_number >= config.max_pages:
                break
            next_button = await select_with_timeout(tab, '.prevNextBut[title="Sonraki"]', timeout=5)
            if not next_button:
                break
            await next_button.click()
            await polite_sleep(config)
    return saved_total


async def run_scraper(config: ScraperConfig) -> int:
    driver = await start_browser(config)
    try:
        return await scrape_with_driver(driver, config)
    finally:
        driver.stop()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect Sahibinden vehicle listing search results.")
    parser.add_argument("--query", required=True, help="Search query, e.g. 'Renault Clio'.")
    parser.add_argument("--year-min", default=None)
    parser.add_argument("--year-max", default=None)
    parser.add_argument("--engine-volume", default=None)
    parser.add_argument("--transmission", default=None, help="manuel or otomatik")
    parser.add_argument("--max-pages", type=int, default=1)
    parser.add_argument("--delay-min", type=float, default=2.5)
    parser.add_argument("--delay-max", type=float, default=5.0)
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--browser-executable-path", default=None, help="Optional Chrome/Edge executable path.")
    parser.add_argument("--user-data-dir", default=None, help="Optional browser profile directory.")
    parser.add_argument("--no-sandbox", action="store_true")
    parser.add_argument("--manual-wait-seconds", type=float, default=0)
    parser.add_argument("--debug-html-path", default=str(DEFAULT_DEBUG_HTML_PATH))
    parser.add_argument("--debug-results-path", default=str(DEFAULT_DEBUG_RESULTS_PATH))
    return parser


def main(argv: Iterable[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    config = ScraperConfig(
        query=args.query,
        year_min=args.year_min,
        year_max=args.year_max,
        engine_volume=args.engine_volume,
        transmission=args.transmission,
        max_pages=args.max_pages,
        delay_min=args.delay_min,
        delay_max=args.delay_max,
        db_path=args.db_path,
        headless=args.headless,
        browser_executable_path=args.browser_executable_path,
        user_data_dir=args.user_data_dir,
        sandbox=not args.no_sandbox,
        manual_wait_seconds=args.manual_wait_seconds,
        debug_html_path=args.debug_html_path,
        debug_results_path=args.debug_results_path,
    )
    saved_total = asyncio.run(run_scraper(config))
    print(f"Saved or updated listings: {saved_total}")


if __name__ == "__main__":
    main()
