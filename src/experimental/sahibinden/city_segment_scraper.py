"""Scrape Sahibinden automobile listings city by city."""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from src.experimental.sahibinden.category_page_scraper import (
    BASE_URL,
    extract_total_count,
    find_browser_executable,
    has_access_challenge,
    has_login_page,
    store_html_page,
)
from src.experimental.sahibinden.scraper import ScraperConfig, start_browser, wait_for_manual_access_check
from src.ingestion.storage import DEFAULT_DB_PATH

CHECKPOINT_PATH = Path("data") / "runtime" / "city_segment_checkpoint.json"
SCRAPER_PROFILE_PATH = Path("data") / "runtime" / "edge-profile-city"


CITY_SEGMENTS = [
    ("Adana", "adana"),
    ("Adıyaman", "adiyaman"),
    ("Afyonkarahisar", "afyonkarahisar"),
    ("Ağrı", "agri"),
    ("Aksaray", "aksaray"),
    ("Amasya", "amasya"),
    ("Ankara", "ankara"),
    ("Antalya", "antalya"),
    ("Ardahan", "ardahan"),
    ("Artvin", "artvin"),
    ("Aydın", "aydin"),
    ("Balıkesir", "balikesir"),
    ("Bartın", "bartin"),
    ("Batman", "batman"),
    ("Bayburt", "bayburt"),
    ("Bilecik", "bilecik"),
    ("Bingöl", "bingol"),
    ("Bitlis", "bitlis"),
    ("Bolu", "bolu"),
    ("Burdur", "burdur"),
    ("Bursa", "bursa"),
    ("Çanakkale", "canakkale"),
    ("Çankırı", "cankiri"),
    ("Çorum", "corum"),
    ("Denizli", "denizli"),
    ("Diyarbakır", "diyarbakir"),
    ("Düzce", "duzce"),
    ("Edirne", "edirne"),
    ("Elazığ", "elazig"),
    ("Erzincan", "erzincan"),
    ("Erzurum", "erzurum"),
    ("Eskişehir", "eskisehir"),
    ("Gaziantep", "gaziantep"),
    ("Giresun", "giresun"),
    ("Gümüşhane", "gumushane"),
    ("Hakkari", "hakkari"),
    ("Hatay", "hatay"),
    ("Iğdır", "igdir"),
    ("Isparta", "isparta"),
    ("İstanbul", "istanbul"),
    ("İzmir", "izmir"),
    ("Kahramanmaraş", "kahramanmaras"),
    ("Karabük", "karabuk"),
    ("Karaman", "karaman"),
    ("Kars", "kars"),
    ("Kastamonu", "kastamonu"),
    ("Kayseri", "kayseri"),
    ("Kırıkkale", "kirikkale"),
    ("Kırklareli", "kirklareli"),
    ("Kırşehir", "kirsehir"),
    ("Kilis", "kilis"),
    ("Kocaeli", "kocaeli"),
    ("Konya", "konya"),
    ("Kütahya", "kutahya"),
    ("Malatya", "malatya"),
    ("Manisa", "manisa"),
    ("Mardin", "mardin"),
    ("Mersin", "mersin"),
    ("Muğla", "mugla"),
    ("Muş", "mus"),
    ("Nevşehir", "nevsehir"),
    ("Niğde", "nigde"),
    ("Ordu", "ordu"),
    ("Osmaniye", "osmaniye"),
    ("Rize", "rize"),
    ("Sakarya", "sakarya"),
    ("Samsun", "samsun"),
    ("Siirt", "siirt"),
    ("Sinop", "sinop"),
    ("Sivas", "sivas"),
    ("Şanlıurfa", "sanliurfa"),
    ("Şırnak", "sirnak"),
    ("Tekirdağ", "tekirdag"),
    ("Tokat", "tokat"),
    ("Trabzon", "trabzon"),
    ("Tunceli", "tunceli"),
    ("Uşak", "usak"),
    ("Van", "van"),
    ("Yalova", "yalova"),
    ("Yozgat", "yozgat"),
    ("Zonguldak", "zonguldak"),
]

CITY_NAME_FIXES = {
    "adiyaman": "Adıyaman",
    "agri": "Ağrı",
    "aydin": "Aydın",
    "balikesir": "Balıkesir",
    "bartin": "Bartın",
    "bingol": "Bingöl",
    "canakkale": "Çanakkale",
    "cankiri": "Çankırı",
    "corum": "Çorum",
    "duzce": "Düzce",
    "elazig": "Elazığ",
    "eskisehir": "Eskişehir",
    "gumushane": "Gümüşhane",
    "igdir": "Iğdır",
    "istanbul": "İstanbul",
    "izmir": "İzmir",
    "kahramanmaras": "Kahramanmaraş",
    "karabuk": "Karabük",
    "kirikkale": "Kırıkkale",
    "kirklareli": "Kırklareli",
    "kirsehir": "Kırşehir",
    "kutahya": "Kütahya",
    "mugla": "Muğla",
    "mus": "Muş",
    "nevsehir": "Nevşehir",
    "nigde": "Niğde",
    "sanliurfa": "Şanlıurfa",
    "sirnak": "Şırnak",
    "tekirdag": "Tekirdağ",
    "usak": "Uşak",
}


@dataclass(frozen=True, slots=True)
class CitySegment:
    name: str
    slug: str

    @property
    def url_base(self) -> str:
        return f"{BASE_URL}/{self.slug}"

    @property
    def display_name(self) -> str:
        return CITY_NAME_FIXES.get(self.slug, self.name)


def load_checkpoint(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"city_index": 0, "offset": 0, "completed": []}
    return json.loads(path.read_text(encoding="utf-8"))


def save_checkpoint(path: Path, *, city_index: int, offset: int, completed: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"city_index": city_index, "offset": offset, "completed": completed}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def build_url(segment: CitySegment, offset: int, page_size: int) -> str:
    parsed = urlparse(segment.url_base)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.update({"pagingSize": str(page_size), "pagingOffset": str(offset)})
    return urlunparse(parsed._replace(query=urlencode(query)))


def load_cities(only_city: str | None = None) -> list[CitySegment]:
    cities = [CitySegment(name=name, slug=slug) for name, slug in CITY_SEGMENTS]
    if not only_city:
        return cities

    normalized = only_city.casefold()
    return [city for city in cities if city.name.casefold() == normalized or city.slug.casefold() == normalized]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scrape Sahibinden automobile category pages city by city.")
    parser.add_argument("--city", default=None, help="Optional single city, e.g. ankara")
    parser.add_argument("--city-limit", type=int, default=None)
    parser.add_argument("--start-offset", type=int, default=None)
    parser.add_argument("--page-size", type=int, default=50, choices=[20, 50])
    parser.add_argument("--pages-per-city", type=int, default=20, help="Use 0 to keep going until the site ends.")
    parser.add_argument("--delay-min", type=float, default=0.7)
    parser.add_argument("--delay-max", type=float, default=1.5)
    parser.add_argument("--manual-wait-seconds", type=float, default=30)
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--checkpoint-path", default=str(CHECKPOINT_PATH))
    parser.add_argument("--reset-checkpoint", action="store_true")
    parser.add_argument("--max-empty-pages", type=int, default=1)
    parser.add_argument("--max-low-change-pages", type=int, default=3)
    parser.add_argument("--stop-on-empty-city", action="store_true")
    return parser


async def run(args: argparse.Namespace) -> None:
    checkpoint_path = Path(args.checkpoint_path)
    if args.reset_checkpoint and checkpoint_path.exists():
        checkpoint_path.unlink()

    checkpoint = load_checkpoint(checkpoint_path)
    completed = [str(item) for item in checkpoint.get("completed", [])]
    cities = load_cities(args.city)
    if not cities:
        available = ", ".join(city.slug for city in load_cities(None))
        raise SystemExit(f"City not found: {args.city}. Available slugs: {available}")
    if args.city_limit is not None:
        cities = cities[: args.city_limit]

    city_index = int(checkpoint.get("city_index", 0)) if not args.city else 0
    if args.start_offset is not None:
        offset = args.start_offset
    elif args.city:
        offset = 0
    else:
        offset = int(checkpoint.get("offset", 0))

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
        cities = cities[city_index:]
        print(
            f"Starting city segmented scrape. cities_remaining={len(cities)} "
            f"city_index={city_index} offset={offset} pages_per_city={args.pages_per_city}",
            flush=True,
        )

        for relative_index, segment in enumerate(cities):
            absolute_index = city_index + relative_index
            city_name = segment.display_name
            current_offset = offset if relative_index == 0 else 0
            empty_pages = 0
            low_change_pages = 0
            city_had_data = False
            total_count = None

            print(f"\nCity {absolute_index + 1}: {city_name} ({segment.url_base})", flush=True)
            max_pages = args.pages_per_city if args.pages_per_city > 0 else 1_000_000
            for page_index in range(1, max_pages + 1):
                url = build_url(segment, current_offset, args.page_size)
                print(f"Opening {url}", flush=True)
                tab = await driver.get(url)
                await wait_for_manual_access_check(tab, config, f"opening {city_name} offset {current_offset}")
                html = await tab.get_content()
                if total_count is None:
                    total_count = extract_total_count(html)
                    print(f"reported_total_count={total_count}", flush=True)

                try:
                    result = store_html_page(
                        html,
                        current_offset,
                        args.page_size,
                        args.db_path,
                        city_override=city_name,
                    )
                except RuntimeError as exc:
                    empty_pages += 1
                    print(f"EMPTY/STOP city={city_name} offset={current_offset} error={exc}", flush=True)
                    if not has_login_page(html) and not has_access_challenge(html):
                        print(f"No listing rows found on a normal page for {city_name}; treating city as complete.", flush=True)
                        city_had_data = city_had_data or current_offset > 0
                        break
                    if empty_pages >= args.max_empty_pages:
                        break
                else:
                    city_had_data = True
                    empty_pages = 0
                    if result.changed <= 1:
                        low_change_pages += 1
                    else:
                        low_change_pages = 0

                    next_offset = current_offset + args.page_size
                    save_checkpoint(
                        checkpoint_path,
                        city_index=absolute_index,
                        offset=next_offset,
                        completed=completed,
                    )
                    print(
                        f"city={city_name} page={page_index} offset={result.offset} "
                        f"parsed={result.parsed} changed={result.changed} stored_total={result.stored_total} "
                        f"next_offset={next_offset} total_count={total_count}",
                        flush=True,
                    )
                    current_offset = next_offset

                    if total_count is not None and current_offset >= total_count:
                        break
                    if args.max_low_change_pages > 0 and low_change_pages >= args.max_low_change_pages:
                        print(f"Low-change page limit reached for {city_name}; moving on.", flush=True)
                        break

                if page_index < max_pages:
                    time.sleep(random.uniform(args.delay_min, args.delay_max))

            if city_had_data:
                if city_name not in completed:
                    completed.append(city_name)
                save_checkpoint(checkpoint_path, city_index=absolute_index + 1, offset=0, completed=completed)
            else:
                if args.stop_on_empty_city:
                    save_checkpoint(checkpoint_path, city_index=absolute_index, offset=current_offset, completed=completed)
                    print(f"City {city_name} did not produce data; keeping it pending.", flush=True)
                    break

                skipped_marker = f"{city_name} (skipped)"
                if skipped_marker not in completed:
                    completed.append(skipped_marker)
                save_checkpoint(checkpoint_path, city_index=absolute_index + 1, offset=0, completed=completed)
                print(f"City {city_name} did not produce data; skipping and continuing.", flush=True)
    finally:
        driver.stop()


def main() -> None:
    args = build_parser().parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
