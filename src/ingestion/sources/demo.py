"""Synthetic listings that let anyone run the product without a data source.

Every value here is generated. Prices follow a simple, documented model (new
price of the trim, yearly depreciation, mileage, condition and a small monthly
drift) plus noise, so the charts and the valuation behave like a real market
without claiming to be one. Rows are stored with ``source = "demo"`` and the API
reports that, so the interface can say so.

Generation is deterministic for a given seed and reference date.
"""

from __future__ import annotations

import math
import random
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, timedelta

from src.ingestion.schema import VehicleListing

DEMO_SOURCE = "demo"

TURKISH_MONTH_NAMES = (
    "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
    "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık",
)

# Listing volume roughly follows population; the weights only shape the demo.
CITY_WEIGHTS = {
    "İstanbul": 30, "Ankara": 12, "İzmir": 9, "Bursa": 6, "Antalya": 5, "Kocaeli": 4,
    "Konya": 4, "Adana": 4, "Gaziantep": 3, "Kayseri": 3, "Mersin": 3, "Eskişehir": 2,
    "Samsun": 2, "Denizli": 2, "Trabzon": 2, "Tekirdağ": 2, "Sakarya": 2, "Manisa": 2,
}
COLORS = ("Beyaz", "Gri", "Siyah", "Füme", "Kırmızı", "Lacivert", "Gümüş Gri", "Mavi")
PART_NAMES = ("sağ ön çamurluk", "sol ön kapı", "kaput", "bagaj kapağı", "sağ arka kapı", "tavan")


@dataclass(frozen=True, slots=True)
class DemoTrim:
    package: str
    fuel_type: str
    transmission: str
    first_year: int
    last_year: int
    price_factor: float = 1.0


@dataclass(frozen=True, slots=True)
class DemoSeries:
    brand: str
    series: str
    body_type: str
    #: Price of a new base trim in TL at the reference date.
    new_price: int
    #: Relative listing volume.
    weight: int
    trims: tuple[DemoTrim, ...]


# Brand, series and package names all exist in data/reference/vehicle_catalog.json
# so the demo data lines up with the dropdowns. A test guards this.
DEMO_SERIES: tuple[DemoSeries, ...] = (
    DemoSeries("Fiat", "Egea", "Sedan", 1_450_000, 14, (
        DemoTrim("1.4 Fire Easy", "Benzin", "Manuel", 2016, 2026),
        DemoTrim("1.3 Multijet Urban", "Dizel", "Manuel", 2016, 2023, 1.08),
        DemoTrim("1.6 Multijet Lounge", "Dizel", "Otomatik", 2016, 2026, 1.24),
    )),
    DemoSeries("Fiat", "Linea", "Sedan", 1_150_000, 4, (
        DemoTrim("1.3 Multijet Active Plus", "Dizel", "Manuel", 2008, 2016),
        DemoTrim("1.4 Fire Active", "Benzin", "Manuel", 2008, 2016, 0.94),
    )),
    DemoSeries("Renault", "Clio", "Hatchback", 1_400_000, 10, (
        DemoTrim("1.0 TCe Joy", "Benzin", "Manuel", 2019, 2026),
        DemoTrim("1.5 dCi Icon", "Dizel", "Manuel", 2013, 2021, 1.10),
        DemoTrim("1.0 TCe Evolution", "Benzin", "Otomatik", 2023, 2026, 1.18),
    )),
    DemoSeries("Renault", "Megane", "Sedan", 1_750_000, 9, (
        DemoTrim("1.3 TCe Joy", "Benzin", "Otomatik", 2020, 2026),
        DemoTrim("1.5 dCi Touch", "Dizel", "Manuel", 2016, 2021, 1.05),
        DemoTrim("1.5 Blue DCI Icon", "Dizel", "Otomatik", 2020, 2026, 1.18),
    )),
    DemoSeries("Renault", "Taliant", "Sedan", 1_200_000, 4, (
        DemoTrim("1.0 Tce Joy", "Benzin", "Manuel", 2021, 2026),
        DemoTrim("1.0 Tce Touch", "Benzin", "Otomatik", 2021, 2026, 1.12),
    )),
    DemoSeries("Toyota", "Corolla", "Sedan", 1_950_000, 9, (
        DemoTrim("1.5 Vision", "Benzin", "Manuel", 2019, 2026),
        DemoTrim("1.5 Dream", "Benzin", "Otomatik", 2019, 2026, 1.12),
        DemoTrim("1.6 Life", "Benzin", "Manuel", 2013, 2018, 0.98),
    )),
    DemoSeries("Volkswagen", "Passat", "Sedan", 3_100_000, 6, (
        DemoTrim("1.6 TDi BlueMotion Comfortline", "Dizel", "Otomatik", 2015, 2020),
        DemoTrim("1.5 TSi Business", "Benzin", "Otomatik", 2020, 2026, 1.06),
        DemoTrim("1.5 TSi Elegance", "Benzin", "Otomatik", 2020, 2026, 1.16),
    )),
    DemoSeries("Volkswagen", "Polo", "Hatchback", 1_550_000, 6, (
        DemoTrim("1.0 Life", "Benzin", "Manuel", 2021, 2026),
        DemoTrim("1.0 TSi Comfortline", "Benzin", "Otomatik", 2018, 2021, 1.08),
        DemoTrim("1.4 TDi Comfortline", "Dizel", "Manuel", 2014, 2018, 0.98),
    )),
    DemoSeries("Volkswagen", "Golf", "Hatchback", 2_250_000, 6, (
        DemoTrim("1.0 eTSI Life", "Benzin", "Otomatik", 2021, 2026),
        DemoTrim("1.5 eTSI Style", "Benzin", "Otomatik", 2021, 2026, 1.14),
        DemoTrim("1.6 TDi Comfortline", "Dizel", "Otomatik", 2013, 2020, 0.96),
    )),
    DemoSeries("Ford", "Focus", "Hatchback", 1_850_000, 7, (
        DemoTrim("1.5 TDCi Trend X", "Dizel", "Manuel", 2015, 2019),
        DemoTrim("1.5 TDCi Titanium", "Dizel", "Otomatik", 2019, 2026, 1.12),
        DemoTrim("1.0 EcoBoost Titanium X", "Benzin", "Otomatik", 2022, 2026, 1.18),
    )),
    DemoSeries("Hyundai", "i20", "Hatchback", 1_350_000, 7, (
        DemoTrim("1.4 MPI Jump", "Benzin", "Manuel", 2020, 2026),
        DemoTrim("1.4 MPI Style", "Benzin", "Otomatik", 2020, 2026, 1.10),
        DemoTrim("1.4 CRDi Style", "Dizel", "Manuel", 2015, 2020, 1.02),
    )),
    DemoSeries("Opel", "Corsa", "Hatchback", 1_450_000, 5, (
        DemoTrim("1.2 Edition", "Benzin", "Manuel", 2020, 2026),
        DemoTrim("1.2 Turbo Elegance", "Benzin", "Otomatik", 2020, 2026, 1.14),
        DemoTrim("1.4 Enjoy", "Benzin", "Manuel", 2011, 2019, 0.95),
    )),
    DemoSeries("Opel", "Astra", "Hatchback", 1_850_000, 6, (
        DemoTrim("1.2 T Edition", "Benzin", "Otomatik", 2022, 2026),
        DemoTrim("1.6 CDTI Dynamic", "Dizel", "Otomatik", 2016, 2021, 1.02),
        DemoTrim("1.4 T Enjoy", "Benzin", "Manuel", 2013, 2019, 0.94),
    )),
    DemoSeries("Peugeot", "208", "Hatchback", 1_500_000, 6, (
        DemoTrim("1.2 PureTech Active", "Benzin", "Manuel", 2019, 2026),
        DemoTrim("1.2 PureTech Allure", "Benzin", "Otomatik", 2020, 2026, 1.14),
        DemoTrim("1.6 BlueHDi Active", "Dizel", "Manuel", 2015, 2019, 1.02),
    )),
    DemoSeries("Dacia", "Sandero", "Hatchback", 1_050_000, 5, (
        DemoTrim("1.0 Tce Comfort", "Benzin", "Manuel", 2021, 2026),
        DemoTrim("0.9 TCe Stepway", "Benzin", "Manuel", 2015, 2020, 1.04),
        DemoTrim("1.5 dCi Stepway", "Dizel", "Manuel", 2013, 2020, 1.06),
    )),
    DemoSeries("Honda", "Civic", "Sedan", 2_150_000, 7, (
        DemoTrim("1.6 i-VTEC ECO Elegance", "Benzin & LPG", "Otomatik", 2016, 2021),
        DemoTrim("1.5 i-VTEC Eco Executive Plus", "Benzin", "Otomatik", 2022, 2026, 1.18),
        DemoTrim("1.6 i-VTEC Premium", "Benzin", "Manuel", 2012, 2016, 0.92),
    )),
    DemoSeries("Skoda", "Octavia", "Sedan", 2_200_000, 4, (
        DemoTrim("1.0 TSI Optimal", "Benzin", "Otomatik", 2020, 2026),
        DemoTrim("1.6 TDI Style", "Dizel", "Otomatik", 2014, 2020, 1.02),
        DemoTrim("1.5 e-Tec Premium", "Benzin", "Otomatik", 2024, 2026, 1.16),
    )),
    DemoSeries("Citroen", "C-Elysee", "Sedan", 1_100_000, 4, (
        DemoTrim("1.6 BlueHDi Feel", "Dizel", "Manuel", 2016, 2022),
        DemoTrim("1.2 PureTech Live", "Benzin", "Manuel", 2016, 2022, 0.93),
    )),
    DemoSeries("Seat", "Leon", "Hatchback", 1_950_000, 4, (
        DemoTrim("1.0 eTSI Style", "Benzin", "Otomatik", 2021, 2026),
        DemoTrim("1.5 eTSI FR", "Benzin", "Otomatik", 2021, 2026, 1.14),
        DemoTrim("1.6 TDI Style", "Dizel", "Otomatik", 2014, 2020, 0.98),
    )),
    DemoSeries("BMW", "3 Serisi", "Sedan", 4_300_000, 5, (
        DemoTrim("320i M Sport", "Benzin", "Otomatik", 2019, 2026, 1.08),
        DemoTrim("320d Sport Line", "Dizel", "Otomatik", 2013, 2019),
        DemoTrim("318i M Sport", "Benzin", "Otomatik", 2019, 2026),
    )),
    DemoSeries("BMW", "5 Serisi", "Sedan", 6_200_000, 3, (
        DemoTrim("520i Luxury Line", "Benzin", "Otomatik", 2017, 2026),
        DemoTrim("520d M Sport", "Dizel", "Otomatik", 2014, 2022, 1.06),
    )),
    DemoSeries("Audi", "A3", "Sedan", 2_750_000, 4, (
        DemoTrim("A3 Sedan 1.5 TFSI Dynamic", "Benzin", "Otomatik", 2017, 2020),
        DemoTrim("A3 Sedan 1.6 TDI Design Line", "Dizel", "Otomatik", 2014, 2019, 0.98),
        DemoTrim("A3 Sedan 1.0 TFSI Design Line", "Benzin", "Otomatik", 2017, 2020, 0.96),
    )),
    DemoSeries("Tesla", "Model Y", "SUV", 2_600_000, 3, (
        DemoTrim("Standart Range", "Elektrik", "Otomatik", 2023, 2026),
        DemoTrim("Long Range AWD", "Elektrik", "Otomatik", 2023, 2026, 1.16),
    )),
    DemoSeries("Tofaş", "Şahin", "Sedan", 700_000, 2, (
        DemoTrim("1.6 ie", "Benzin & LPG", "Manuel", 1995, 2002),
        DemoTrim("1.4", "Benzin", "Manuel", 1990, 1996, 0.92),
    )),
)


@dataclass(frozen=True, slots=True)
class DemoConfig:
    count: int = 6000
    seed: int = 2026
    #: Listing dates are spread over this many days before the reference date.
    history_days: int = 120
    #: Average monthly asking-price drift across the market.
    monthly_drift: float = 0.018


def turkish_date(value: date) -> str:
    """Format a date the way the listing parsers already understand."""
    return f"{value.day} {TURKISH_MONTH_NAMES[value.month - 1]} {value.year}"


def _depreciation(age: int) -> float:
    # A new car loses most in its first year, then roughly 7% a year, with a
    # floor so old but running cars keep a realistic residual value.
    if age <= 0:
        return 1.0
    return max(0.88 * 0.93 ** (age - 1), 0.25)


def _mileage(rng: random.Random, age: int) -> int:
    expected = max(age, 0.3) * 17_000
    return min(450_000, max(0, int(round(expected * rng.lognormvariate(0, 0.35), -2))))


def _mileage_factor(age: int, mileage_km: int) -> float:
    expected = max(age, 0.3) * 17_000
    return math.exp(-0.12 * (mileage_km - expected) / 50_000)


def _condition(rng: random.Random, age: int) -> tuple[int, int]:
    """Return painted and changed part counts; older cars have more history."""
    painted = min(6, int(rng.expovariate(1.6 - min(age, 12) * 0.07)))
    changed = min(3, int(rng.expovariate(3.0 - min(age, 12) * 0.12)))
    return painted, changed


def _title(rng: random.Random, series: DemoSeries, trim: DemoTrim, year: int, painted: int, changed: int) -> str:
    base = f"{year} {series.brand} {series.series} {trim.package}"
    if painted == 0 and changed == 0:
        return f"{base} boyasız değişensiz"
    if changed == 0 and rng.random() < 0.5:
        return f"{base} değişensiz"
    return base


def demo_reference_values(reference_date: date) -> list[tuple[str, str, int, float]]:
    """A synthetic kasko list for the demo: (brand, tip, model year, value).

    It follows the same price model as the demo listings without their noise,
    written the way the published list names vehicles.
    """
    rows = []
    for series in DEMO_SERIES:
        for trim in series.trims:
            for year in range(trim.first_year, min(trim.last_year, reference_date.year) + 1):
                value = series.new_price * trim.price_factor * _depreciation(reference_date.year - year) * 1.03
                # Lists name BMW-style series by the model code alone ("320i M Sport").
                prefix = "" if series.series.endswith("Serisi") else f"{series.series} "
                tip = f"{prefix}{trim.package}".upper()
                rows.append((series.brand.upper(), tip, year, float(round(value, -3))))
    return rows


class DemoSource:
    """Deterministic synthetic listings for demos, screenshots and tests."""

    name = DEMO_SOURCE

    def __init__(self, config: DemoConfig | None = None, reference_date: date | None = None) -> None:
        self.config = config or DemoConfig()
        self.reference_date = reference_date or date.today()

    def listings(self) -> Iterator[VehicleListing]:
        rng = random.Random(self.config.seed)
        weights = [series.weight for series in DEMO_SERIES]
        # Each series drifts at its own pace so market movers have something to show.
        series_drift = {series.series: rng.uniform(-0.6, 1.8) for series in DEMO_SERIES}
        cities, city_weights = zip(*CITY_WEIGHTS.items(), strict=True)
        max_year = self.reference_date.year

        for index in range(self.config.count):
            series = rng.choices(DEMO_SERIES, weights=weights)[0]
            trim = rng.choice(series.trims)
            year = rng.randint(trim.first_year, min(trim.last_year, max_year))
            age = max_year - year
            mileage_km = _mileage(rng, age)
            painted, changed = _condition(rng, age)

            # Newer listings are somewhat more common, like on a real marketplace,
            # while every day keeps enough listings for a readable daily trend.
            days_ago = int(self.config.history_days * rng.random() ** 1.3)
            listing_day = self.reference_date - timedelta(days=days_ago)
            months_ago = days_ago / 30.4
            drift = (1 + self.config.monthly_drift * series_drift[series.series]) ** -months_ago

            price = (
                series.new_price * trim.price_factor
                * _depreciation(age)
                * _mileage_factor(age, mileage_km)
                * (1 - 0.015 * painted - 0.04 * changed)
                * (1.04 if trim.transmission == "Otomatik" and trim.fuel_type != "Elektrik" else 1.0)
                * drift
                * rng.lognormvariate(0, 0.07)
            )
            price = max(int(round(price, -3)), 60_000)

            yield VehicleListing.create(
                source=DEMO_SOURCE,
                source_listing_id=f"demo-{self.config.seed}-{index}",
                title=_title(rng, series, trim, year, painted, changed),
                brand=series.brand,
                series=series.series,
                model=trim.package,
                year=year,
                mileage_km=mileage_km,
                transmission=trim.transmission,
                fuel_type=trim.fuel_type,
                body_type=series.body_type,
                color=rng.choice(COLORS),
                city=rng.choices(cities, weights=city_weights)[0],
                seller_type=rng.choices(("Sahibinden", "Galeriden"), weights=(55, 45))[0],
                price=price,
                listing_date=turkish_date(listing_day),
                paint_status="Boyasız" if painted == 0 else f"{painted} parça boyalı",
                changed_part_status="Değişensiz" if changed == 0 else ", ".join(rng.sample(PART_NAMES, changed)),
                is_clean_claimed=int(painted == 0 and changed == 0),
                scrape_segment=DEMO_SOURCE,
            )
