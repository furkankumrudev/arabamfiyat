"""Market analysis engine for vehicle listing comparisons."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True, slots=True)
class MarketAnalysisConfig:
    """Tuning knobs for the market engine."""

    min_sample_size: int = 8
    max_year_distance: int = 6
    mileage_tolerance_ratio: float = 0.30
    minimum_mileage_tolerance: int = 25_000


@dataclass(slots=True)
class MarketAnalysisRequest:
    """User-selected context for one market comparison."""

    listings: pd.DataFrame
    target_year: int | None = None
    target_mileage: int | None = None
    selected_model: str | None = None
    user_price: int | None = None


def _weighted_quantile(values: pd.Series, weights: pd.Series, quantile: float) -> float:
    data = pd.DataFrame({"value": values, "weight": weights}).dropna()
    data = data[(data["weight"] > 0) & (data["value"] > 0)]
    if data.empty:
        return float("nan")

    data = data.sort_values("value")
    cumulative_weight = data["weight"].cumsum()
    cutoff = quantile * data["weight"].sum()
    return float(data.loc[cumulative_weight >= cutoff, "value"].iloc[0])


def _price_summary(df: pd.DataFrame, weight_column: str = "similarity_score") -> dict[str, float | int]:
    prices = df["price"].dropna()
    if prices.empty:
        return {}

    weights = df.get(weight_column, pd.Series(1.0, index=df.index)).fillna(1.0)
    return {
        "count": int(prices.count()),
        "min": float(prices.min()),
        "q1": float(prices.quantile(0.25)),
        "median": float(prices.quantile(0.50)),
        "q3": float(prices.quantile(0.75)),
        "max": float(prices.max()),
        "mean": float(prices.mean()),
        "weighted_q1": _weighted_quantile(prices, weights, 0.25),
        "weighted_median": _weighted_quantile(prices, weights, 0.50),
        "weighted_q3": _weighted_quantile(prices, weights, 0.75),
        "weighted_mean": float(np.average(prices, weights=weights.loc[prices.index])),
    }


def _remove_price_outliers(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    prices = df["price"].dropna()
    if len(prices) < 12:
        return df.copy(), 0

    q1 = prices.quantile(0.25)
    q3 = prices.quantile(0.75)
    iqr = q3 - q1
    if iqr <= 0:
        return df.copy(), 0

    lower = max(float(q1 - 1.5 * iqr), float(prices.quantile(0.02)))
    upper = min(float(q3 + 1.5 * iqr), float(prices.quantile(0.98)))
    cleaned = df[(df["price"].isna()) | (df["price"].between(lower, upper))].copy()
    return cleaned, int(len(df) - len(cleaned))


def _score_by_distance(values: pd.Series, target: float | int | None, scale: float) -> pd.Series:
    if target is None or pd.isna(target) or scale <= 0:
        return pd.Series(0.65, index=values.index)

    numeric = pd.to_numeric(values, errors="coerce")
    distance = (numeric - float(target)).abs()
    score = 1 - (distance / scale)
    score = score.clip(lower=0, upper=1)
    return score.fillna(0.55)


def _freshness_score(df: pd.DataFrame) -> pd.Series:
    if "parsed_listing_date" not in df or df["parsed_listing_date"].dropna().empty:
        return pd.Series(0.65, index=df.index)

    dates = pd.to_datetime(df["parsed_listing_date"], errors="coerce")
    newest = dates.max()
    age_days = (newest - dates).dt.days
    score = 1 - (age_days / 45)
    return score.clip(lower=0.35, upper=1).fillna(0.55)


class MarketAnalysisEngine:
    """Scores similar listings and turns them into market guidance."""

    def __init__(self, config: MarketAnalysisConfig | None = None) -> None:
        self.config = config or MarketAnalysisConfig()

    def analyze(self, request: MarketAnalysisRequest) -> dict[str, object]:
        if request.listings.empty or "price" not in request.listings:
            return {"status": "empty", "count": 0}

        candidates = request.listings.dropna(subset=["price"]).copy()
        if candidates.empty:
            return {"status": "empty", "count": 0}

        candidates = self._score_candidates(candidates, request)
        scored_candidates, selection_note = self._select_context_candidates(candidates, request)
        if scored_candidates.empty:
            return {
                "status": "empty",
                "count": 0,
                "raw_count": int(len(candidates)),
                "selected_count": 0,
                "selection_note": selection_note,
            }
        cleaned, outlier_count = _remove_price_outliers(scored_candidates)
        summary = _price_summary(cleaned)
        if not summary:
            return {"status": "empty", "count": 0}

        count = int(summary["count"])
        market_position, price_delta_pct = self._compare_user_price(summary, request.user_price)
        return {
            "status": "ok" if count >= self.config.min_sample_size else "low_sample",
            "summary": summary,
            "count": count,
            "raw_count": int(len(candidates)),
            "selected_count": int(len(scored_candidates)),
            "used_count": int(len(cleaned)),
            "outlier_count": outlier_count,
            "selection_note": selection_note,
            "confidence": self._confidence_label(count),
            "market_position": market_position,
            "price_delta_pct": price_delta_pct,
            "scored_listings": candidates,
            "used_listings": cleaned,
        }

    def _score_candidates(self, candidates: pd.DataFrame, request: MarketAnalysisRequest) -> pd.DataFrame:
        scored = candidates.copy()
        model_score = self._model_score(scored, request.selected_model)
        year_score = _score_by_distance(
            scored.get("year", pd.Series(index=scored.index)),
            request.target_year,
            self.config.max_year_distance,
        )
        mileage_scale = max(float(request.target_mileage or 100_000) * 0.75, 80_000)
        mileage_score = _score_by_distance(
            scored.get("mileage_km", pd.Series(index=scored.index)),
            request.target_mileage,
            mileage_scale,
        )
        scored["similarity_score"] = (
            0.42 * year_score
            + 0.34 * mileage_score
            + 0.14 * model_score
            + 0.10 * _freshness_score(scored)
        ).clip(lower=0.05, upper=1)
        return scored.sort_values("similarity_score", ascending=False)

    def _model_score(self, candidates: pd.DataFrame, selected_model: str | None) -> pd.Series:
        target_model_key = str(selected_model or "").strip().casefold()
        target_model_ascii = unicodedata.normalize("NFKD", target_model_key).encode("ascii", "ignore").decode("ascii")
        if not target_model_key or target_model_ascii in {"tum", "tumu"}:
            return pd.Series(0.75, index=candidates.index)

        haystack = (
            candidates.get("model", "").fillna("").astype(str)
            + " "
            + candidates.get("title", "").fillna("").astype(str)
        ).str.casefold()
        return pd.Series(
            np.where(haystack.str.contains(target_model_key, regex=False), 1.0, 0.65),
            index=candidates.index,
        )

    def _select_context_candidates(
        self, candidates: pd.DataFrame, request: MarketAnalysisRequest
    ) -> tuple[pd.DataFrame, str]:
        """Keep every listing inside a transparent year/mileage context window."""
        if request.target_year is None and request.target_mileage is None:
            return candidates.copy(), "Seçilen modeldeki tüm eşleşen ilanlar kullanıldı."

        selected = candidates.copy()
        criteria: list[str] = []
        if request.target_year is not None:
            years = pd.to_numeric(
                selected.get("year", pd.Series(index=selected.index, dtype=float)), errors="coerce"
            )
            selected = selected[years.eq(request.target_year)].copy()
            criteria.append(f"{request.target_year} model yılı")

        if request.target_mileage is not None:
            tolerance = max(
                int(request.target_mileage * self.config.mileage_tolerance_ratio),
                self.config.minimum_mileage_tolerance,
            )
            mileage_lower = max(0, request.target_mileage - tolerance)
            mileage_upper = request.target_mileage + tolerance
            mileages = pd.to_numeric(
                selected.get("mileage_km", pd.Series(index=selected.index, dtype=float)), errors="coerce"
            )
            selected = selected[mileages.between(mileage_lower, mileage_upper)].copy()
            criteria.append(f"{mileage_lower:,}-{mileage_upper:,} km".replace(",", "."))

        return selected, "Yakınlık aralığı: " + " · ".join(criteria)

    def _confidence_label(self, count: int) -> str:
        # These reach the user as written, so they carry their diacritics.
        if count >= 50:
            return "Yüksek"
        if count >= 20:
            return "Orta"
        if count >= self.config.min_sample_size:
            return "Düşük"
        return "Yetersiz"

    def _compare_user_price(self, summary: dict[str, float | int], user_price: int | None) -> tuple[str | None, float | None]:
        if user_price is None or pd.isna(user_price):
            return None, None

        median = float(summary["weighted_median"])
        price_delta_pct = ((float(user_price) - median) / median * 100) if median else None
        if price_delta_pct is None:
            return None, None
        if price_delta_pct <= -8:
            return "Piyasa alti", price_delta_pct
        if price_delta_pct >= 8:
            return "Piyasa ustu", price_delta_pct
        return "Piyasa icinde", price_delta_pct


def build_market_analysis(
    listings: pd.DataFrame,
    *,
    target_year: int | None = None,
    target_mileage: int | None = None,
    selected_model: str | None = None,
    user_price: int | None = None,
    config: MarketAnalysisConfig | None = None,
) -> dict[str, object]:
    """Create a robust market analysis from already-filtered listing rows."""

    request = MarketAnalysisRequest(
        listings=listings,
        target_year=target_year,
        target_mileage=target_mileage,
        selected_model=selected_model,
        user_price=user_price,
    )
    return MarketAnalysisEngine(config).analyze(request)
