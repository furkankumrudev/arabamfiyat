"""Market and valuation calculations built on real cleaned listings."""

from __future__ import annotations

from contextlib import closing
from math import ceil, sqrt
from typing import Any

import pandas as pd

from src.analysis.market_engine import build_market_analysis
from src.ml.predict_price_model import DEFAULT_MODEL_PATH, ConditionAdjustment, estimate_condition_adjustment

from ..database import ListingRepository
from ..services.reference_service import lookup_reference_value
from ..services.trend_service import build_listing_trend, snapshot_changes, unavailable_changes

MIN_RELATIONSHIP_SAMPLE = 3
MILEAGE_BANDS = (
    (0, 25_000, "0-25 bin km"),
    (25_001, 50_000, "25-50 bin km"),
    (50_001, 75_000, "50-75 bin km"),
    (75_001, 100_000, "75-100 bin km"),
    (100_001, 150_000, "100-150 bin km"),
    (150_001, 200_000, "150-200 bin km"),
    (200_001, 300_000, "200-300 bin km"),
    (300_001, 500_000, "300-500 bin km"),
    (500_001, None, "500 bin km+"),
)


def _snapshot_scope(filters: dict[str, Any]) -> tuple[str, str] | None:
    """Use only snapshot dimensions that exactly match the active analysis scope."""
    active = {key: value for key, value in filters.items() if value is not None and value != ""}
    if not active:
        return "market", "all"
    if set(active) == {"brand"}:
        return "brand", str(active["brand"])
    return None


def overview(repository: ListingRepository, filters: dict[str, Any]) -> dict[str, object]:
    listings = repository.load_listings(filters)
    if listings.empty:
        return {
            "median_price": None, "average_price": None, "listing_count": 0,
            "last_updated_at": repository.last_updated_at(), "source_status": "Veri yok",
            "message": "Seçilen filtreler için yeterli ilan bulunamadı.",
        }
    scope = _snapshot_scope(filters)
    with closing(repository.connect()) as connection:
        changes = snapshot_changes(connection, *scope) if scope else unavailable_changes()
    return {
        "median_price": float(listings.price.median()),
        "average_price": float(listings.price.mean()),
        "listing_count": int(len(listings)),
        "last_updated_at": repository.last_updated_at(),
        "source_status": "Temizlenmiş ilan verisi",
        **changes,
    }


def grouped_table(repository: ListingRepository, filters: dict[str, Any], group_by: str) -> list[dict[str, object]]:
    allowed = {"brand": "brand", "body_type": "body_type", "fuel_type": "fuel_type"}
    column = allowed.get(group_by, "brand")
    listings = repository.load_listings(filters)
    if listings.empty or column not in listings:
        return []
    frame = listings.dropna(subset=[column]).copy()
    frame[column] = frame[column].astype(str).str.strip()
    frame = frame[frame[column].ne("")]
    if frame.empty:
        return []
    grouped = frame.groupby(column, as_index=False).agg(
        average_price=("price", "mean"), median_price=("price", "median"), listing_count=("price", "count")
    ).sort_values(["listing_count", "median_price"], ascending=[False, False]).head(100)
    # Snapshots summarise each brand over all of its listings, so their changes
    # only describe a row when no other filter narrows it.
    active = {key for key, value in filters.items() if value is not None and value != ""}
    with_changes = column == "brand" and active <= {"brand"}
    rows = []
    with closing(repository.connect()) as connection:
        for label, average, median, count in grouped.itertuples(index=False, name=None):
            changes = snapshot_changes(connection, "brand", str(label)) if with_changes else unavailable_changes()
            rows.append({
                "label": str(label), "average_price": float(average), "median_price": float(median),
                "listing_count": int(count), **changes,
            })
    return rows


def build_price_relationships(listings: pd.DataFrame) -> dict[str, list[dict[str, object]]]:
    """Summarize real listing prices by model year and mileage bands."""
    if listings.empty:
        return {"year_points": [], "mileage_points": []}

    year_points: list[dict[str, object]] = []
    if "year" in listings:
        years = listings.dropna(subset=["year"]).copy()
        years["year"] = pd.to_numeric(years["year"], errors="coerce")
        years = years[years["year"].between(1950, 2100)]
        grouped_years = years.groupby("year", as_index=False).agg(
            median_price=("price", "median"), average_price=("price", "mean"), listing_count=("price", "count")
        )
        for row in grouped_years[grouped_years["listing_count"] >= MIN_RELATIONSHIP_SAMPLE].sort_values("year").itertuples(index=False):
            year_points.append({
                "label": str(int(row.year)), "median_price": float(row.median_price),
                "average_price": float(row.average_price), "listing_count": int(row.listing_count),
            })

    mileage_points: list[dict[str, object]] = []
    if "mileage_km" in listings:
        mileages = listings.dropna(subset=["mileage_km"]).copy()
        mileages["mileage_km"] = pd.to_numeric(mileages["mileage_km"], errors="coerce")
        mileages = mileages[mileages["mileage_km"] >= 0]
        for minimum, maximum, label in MILEAGE_BANDS:
            mask = mileages["mileage_km"] >= minimum
            if maximum is not None:
                mask &= mileages["mileage_km"] <= maximum
            band = mileages[mask]
            if len(band) < MIN_RELATIONSHIP_SAMPLE:
                continue
            mileage_points.append({
                "label": label, "median_price": float(band["price"].median()),
                "average_price": float(band["price"].mean()), "listing_count": int(len(band)),
            })

    return {"year_points": year_points, "mileage_points": mileage_points}


def price_relationships(repository: ListingRepository, filters: dict[str, Any]) -> dict[str, object]:
    listings = repository.load_listings(filters)
    points = build_price_relationships(listings)
    clean_listings = listings[listings.get("is_clean_claimed", 0).fillna(0).astype(int) == 1] if "is_clean_claimed" in listings else listings.iloc[0:0]
    clean_points = build_price_relationships(clean_listings)
    has_data = bool(points["year_points"] or points["mileage_points"])
    return {
        "listing_count": int(len(listings)),
        "clean_listing_count": int(len(clean_listings)),
        "year_available": bool(points["year_points"]),
        "mileage_available": bool(points["mileage_points"]),
        "clean_year_available": bool(clean_points["year_points"]),
        "clean_mileage_available": bool(clean_points["mileage_points"]),
        **points,
        "clean_year_points": clean_points["year_points"],
        "clean_mileage_points": clean_points["mileage_points"],
        "message": None if has_data else "Yil veya kilometre karsilastirmasi icin yeterli ilan yok.",
    }


def movers(repository: ListingRepository, direction: str) -> list[dict[str, object]]:
    """Return only true snapshot movement; empty is more honest than guesses."""
    with closing(repository.connect()) as connection:
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='market_price_snapshots'"
        ).fetchone()
        if not exists:
            return []
        rows = connection.execute(
            """WITH ranked AS (
                SELECT dimension_value, snapshot_date, median_price, average_price, listing_count,
                       ROW_NUMBER() OVER (PARTITION BY dimension_value ORDER BY snapshot_date DESC) AS rn
                FROM market_price_snapshots WHERE dimension_type='brand'
            )
            SELECT latest.dimension_value, latest.average_price, latest.listing_count,
                   latest.median_price, previous.median_price
            FROM ranked latest JOIN ranked previous ON latest.dimension_value=previous.dimension_value
            WHERE latest.rn=1 AND previous.rn=2"""
        ).fetchall()
    items = []
    for row in rows:
        baseline = float(row[4])
        if not baseline:
            continue
        change = (float(row[3]) - baseline) / baseline * 100
        if (direction == "up" and change > 0) or (direction == "down" and change < 0):
            items.append({
                "label": str(row[0]), "average_price": float(row[1]), "listing_count": int(row[2]),
                "change_percent": change, "direction": "up" if change > 0 else "down",
            })
    return sorted(items, key=lambda item: item["change_percent"], reverse=direction == "up")[:4]


def condition_adjustment_from_payload(payload: dict[str, Any]) -> tuple[ConditionAdjustment | None, str | None]:
    """Estimate only the paint/change discount, never a second standalone price."""
    required = ("brand", "series", "model", "year", "mileage_km")
    if any(payload.get(field) in (None, "") for field in required):
        return None, None
    changed_parts = payload.get("changed_parts")
    painted_parts = payload.get("painted_parts")
    if changed_parts is None and painted_parts is None:
        return None, None
    if not DEFAULT_MODEL_PATH.exists():
        return None, "Boya ve değişen etkisi modeli henüz eğitilmemiş."

    model_payload = {
        "marka": payload.get("brand"),
        "seri": payload.get("series"),
        "model": payload.get("model"),
        "yil": payload.get("year"),
        "kilometre": payload.get("mileage_km"),
        "degisen_sayisi": changed_parts or 0,
        "boyali_sayisi": painted_parts or 0,
    }
    try:
        adjustment = estimate_condition_adjustment(model_payload)
    except (FileNotFoundError, RuntimeError, ValueError) as error:
        return None, f"Boya ve değişen etkisi hesaplanamadı: {error}"

    if adjustment.percent == 0:
        return adjustment, "0 boya ve 0 değişen referans kabul edildi; güncel piyasa fiyatı değişmedi."
    note = "Kaggle verisinde aynı araç yapısında boya ve değişen farkından öğrenilen oran, güncel piyasa değerine uygulandı."
    if adjustment.capped:
        note += " Aşırı oran güvenli aralıkta sınırlandı."
    return adjustment, note


def enrich_condition_payload(
    payload: dict[str, Any], reference_listings: pd.DataFrame,
) -> tuple[dict[str, Any], str | None]:
    """Fill omitted year and mileage from the actual comparable-listing group.

    Paint and changed-part counts still affect a valuation when the user wants a
    broad model comparison. The fallback comes from the same listings used for
    the live market value, rather than an arbitrary default vehicle.
    """
    if payload.get("changed_parts") is None and payload.get("painted_parts") is None:
        return payload, None

    enriched = dict(payload)
    used_fields: list[str] = []
    if enriched.get("year") is None and "year" in reference_listings:
        years = pd.to_numeric(reference_listings["year"], errors="coerce").dropna()
        if not years.empty:
            enriched["year"] = int(years.median())
            used_fields.append("model yılı")
    if enriched.get("mileage_km") is None and "mileage_km" in reference_listings:
        mileages = pd.to_numeric(reference_listings["mileage_km"], errors="coerce").dropna()
        if not mileages.empty:
            enriched["mileage_km"] = int(mileages.median())
            used_fields.append("kilometre")

    if not used_fields:
        return enriched, None
    return enriched, f"{', '.join(used_fields).capitalize()} girilmediği için referans ilan grubunun medyanı kullanıldı."


def _assess_asking_price(market_value: float, asking_price: int | None) -> tuple[str | None, float | None]:
    if asking_price is None or market_value <= 0:
        return None, None
    difference = (float(asking_price) - market_value) / market_value * 100
    if difference <= -8:
        return "Piyasa altı", difference
    if difference >= 8:
        return "Piyasa üstü", difference
    return "Piyasa içinde", difference


def build_comparison_summary(
    listings: pd.DataFrame, *, matched_listing_count: int, selected_listing_count: int,
    outlier_count: int, selection_mode: str, selection_note: str, clean_only: bool,
) -> dict[str, int | str | None]:
    """Return concise, source-free context for the comparable listing group."""
    years = pd.to_numeric(listings.get("year"), errors="coerce").dropna() if "year" in listings else pd.Series(dtype=float)
    mileages = pd.to_numeric(listings.get("mileage_km"), errors="coerce").dropna() if "mileage_km" in listings else pd.Series(dtype=float)
    return {
        "matched_listing_count": matched_listing_count,
        "selected_listing_count": selected_listing_count,
        "used_listing_count": int(len(listings)),
        "outlier_count": outlier_count,
        "selection_mode": selection_mode,
        "selection_note": selection_note,
        "clean_only": clean_only,
        "median_year": int(years.median()) if not years.empty else None,
        "median_mileage_km": int(mileages.median()) if not mileages.empty else None,
    }


def build_reference_price_points(
    listings: pd.DataFrame, *, adjustment_factor: float = 1.0,
) -> list[dict[str, float | int | None]]:
    """Return one display-safe point per analyzed listing for a price strip plot."""
    if listings.empty or "price" not in listings:
        return []
    frame = listings.copy()
    frame["price"] = pd.to_numeric(frame["price"], errors="coerce") * adjustment_factor
    frame = frame[frame["price"] > 0].copy()
    if frame.empty:
        return []

    years = pd.to_numeric(frame["year"], errors="coerce") if "year" in frame else pd.Series(index=frame.index)
    mileages = pd.to_numeric(frame["mileage_km"], errors="coerce") if "mileage_km" in frame else pd.Series(index=frame.index)
    points: list[dict[str, float | int | None]] = []
    for index, row in frame.sort_values("price").iterrows():
        year = years.get(index)
        mileage = mileages.get(index)
        points.append({
            "price": float(row["price"]),
            "year": int(year) if pd.notna(year) else None,
            "mileage_km": int(mileage) if pd.notna(mileage) else None,
        })
    return points


def build_reference_mileage_points(
    listings: pd.DataFrame, *, adjustment_factor: float = 1.0,
) -> list[dict[str, float | int]]:
    """Show price movement across mileage bands from the exact reference group."""
    if listings.empty or not {"mileage_km", "price"}.issubset(listings.columns):
        return []

    frame = listings[["mileage_km", "price"]].copy()
    frame["mileage_km"] = pd.to_numeric(frame["mileage_km"], errors="coerce")
    frame["price"] = pd.to_numeric(frame["price"], errors="coerce") * adjustment_factor
    frame = frame.dropna(subset=["mileage_km", "price"])
    frame = frame[(frame["mileage_km"] >= 0) & (frame["price"] > 0)]
    if frame.empty:
        return []

    minimum = float(frame["mileage_km"].min())
    maximum = float(frame["mileage_km"].max())
    if minimum == maximum:
        return [{
            "lower_mileage_km": int(minimum), "upper_mileage_km": int(maximum),
            "median_price": float(frame["price"].median()), "average_price": float(frame["price"].mean()),
            "listing_count": int(len(frame)),
        }]

    bucket_count = min(8, max(3, ceil(sqrt(len(frame)))))
    step = (maximum - minimum) / bucket_count
    points: list[dict[str, float | int]] = []
    for index in range(bucket_count):
        lower = minimum + step * index
        upper = maximum if index == bucket_count - 1 else minimum + step * (index + 1)
        matches = frame["mileage_km"].between(lower, upper, inclusive="both" if index == bucket_count - 1 else "left")
        band = frame[matches]
        if band.empty:
            continue
        points.append({
            "lower_mileage_km": int(round(lower)), "upper_mileage_km": int(round(upper)),
            "median_price": float(band["price"].median()), "average_price": float(band["price"].mean()),
            "listing_count": int(len(band)),
        })
    return points


def build_reference_listing_trend(
    listings: pd.DataFrame, *, adjustment_factor: float = 1.0,
) -> list[dict[str, object]]:
    """Aggregate listed prices by their real publication date without inventing history."""
    if listings.empty or "listing_date" not in listings:
        return []
    frame = listings.copy()
    frame["price"] = pd.to_numeric(frame["price"], errors="coerce") * adjustment_factor
    points = build_listing_trend(frame)
    return points if len(points) >= 2 else []


def valuation(repository: ListingRepository, payload: dict[str, Any]) -> dict[str, object]:
    filters = {
        key: payload.get(key)
        for key in ("brand", "series", "model", "year_min", "year_max", "mileage_max", "clean_only")
    }
    listings = repository.load_listings(filters)
    reference = reference_value(repository, payload)
    result = build_market_analysis(
        listings, target_year=payload.get("year"), target_mileage=payload.get("mileage_km"),
        selected_model=payload.get("model"), user_price=payload.get("asking_price"),
    )
    if result.get("status") == "empty":
        matched_count = int(result.get("raw_count", 0))
        selection_note = str(result.get("selection_note") or "")
        detail = (
            f"Seçilen modelde {matched_count} ilan var; ancak {selection_note.casefold()} içinde ilan bulunamadı. "
            "Daha yakın bir sonuç için yıl veya kilometre bilgisini güncelleyebilir, alanlardan birini boş bırakabilirsiniz."
            if matched_count and selection_note
            else "Bu araç için yeterli benzer ilan bulunamadı. Filtreleri genişletmeyi deneyin."
        )
        return {
            "status": "empty", "listing_count": 0,
            "explanation": detail,
            "reference_value": reference,
        }
    condition_payload, fallback_note = enrich_condition_payload(payload, result["used_listings"])
    adjustment, adjustment_note = condition_adjustment_from_payload(condition_payload)
    if adjustment_note and fallback_note:
        adjustment_note = f"{adjustment_note} {fallback_note}"
    summary = result["summary"]
    comparison_summary = build_comparison_summary(
        result["used_listings"],
        matched_listing_count=int(result["raw_count"]),
        selected_listing_count=int(result["selected_count"]),
        outlier_count=int(result["outlier_count"]),
        selection_mode="all_matching" if payload.get("year") is None and payload.get("mileage_km") is None else "context_window",
        selection_note=str(result["selection_note"]),
        clean_only=bool(payload.get("clean_only")),
    )
    condition_factor = adjustment.factor if adjustment else 1.0
    reference_price_points = build_reference_price_points(
        result["used_listings"], adjustment_factor=condition_factor,
    )
    reference_mileage_points = build_reference_mileage_points(
        result["used_listings"], adjustment_factor=condition_factor,
    )
    reference_listing_trend = build_reference_listing_trend(
        result["used_listings"], adjustment_factor=condition_factor,
    )
    market_value = float(summary["weighted_median"]) * condition_factor
    low_price = float(summary["weighted_q1"]) * condition_factor
    high_price = float(summary["weighted_q3"]) * condition_factor
    median_price = float(summary["median"]) * condition_factor
    price_assessment, asking_price_delta = _assess_asking_price(market_value, payload.get("asking_price"))
    explanation = (
        "Tahmin; aynı araç grubundaki ilanların yıl, kilometre, model yakınlığı ve güncelliğine göre "
        "puanlanması, ardından aykırı fiyatların dışarıda bırakılmasıyla oluşturuldu."
    )
    if adjustment and adjustment.percent != 0:
        explanation += " Boya ve değişen durumu için Kaggle'dan öğrenilen oran güncel piyasa değerine eklendi."
    return {
        "status": str(result["status"]),
        "estimated_market_value": market_value,
        "recommended_low_price": low_price,
        "recommended_high_price": high_price,
        "median_price": median_price,
        "listing_count": int(result["count"]), "confidence": str(result["confidence"]),
        "price_assessment": price_assessment, "asking_price_delta_percent": asking_price_delta,
        "asking_price": payload.get("asking_price"),
        "explanation": explanation,
        "comparison_summary": comparison_summary,
        "reference_price_points": reference_price_points,
        "reference_mileage_points": reference_mileage_points,
        "reference_listing_trend": reference_listing_trend,
        "condition_adjustment_percent": adjustment.percent if adjustment else None,
        "condition_adjustment_note": adjustment_note,
        "reference_value": _with_market_ratio(reference, market_value),
    }


def reference_value(repository: ListingRepository, payload: dict[str, Any]) -> dict[str, object] | None:
    """The kasko reference value needs a model year; without one there is nothing to look up."""
    if payload.get("year") is None:
        return None
    with closing(repository.connect()) as connection:
        return lookup_reference_value(
            connection, payload.get("brand"), payload.get("series"), payload.get("model"), payload.get("year"),
        )


def _with_market_ratio(reference: dict[str, object] | None, market_value: float) -> dict[str, object] | None:
    if not reference or not reference.get("value"):
        return reference
    return {**reference, "market_to_reference_percent": market_value / float(reference["value"]) * 100}


def serialize_listings(frame: pd.DataFrame, limit: int = 12) -> list[dict[str, object]]:
    fields = ["id", "title", "brand", "series", "model", "year", "mileage_km", "price", "city", "listing_date", "listing_url", "similarity_score"]
    records: list[dict[str, object]] = []
    for item in frame.head(limit).to_dict(orient="records"):
        record = {field: item.get(field) for field in fields}
        for numeric in ("id", "year", "mileage_km"):
            if pd.notna(record.get(numeric)):
                record[numeric] = int(record[numeric])
            else:
                record[numeric] = None
        for numeric in ("price", "similarity_score"):
            if pd.notna(record.get(numeric)):
                record[numeric] = float(record[numeric])
            else:
                record[numeric] = None
        record["title"] = str(record.get("title") or "İlan")
        records.append(record)
    return records
