"""Estimate paint and changed-part adjustments from the Kaggle condition model."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .train_price_model import CATEGORICAL_FEATURES, FEATURE_COLUMNS, NUMERIC_FEATURES, normalize_text

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL_PATH = PROJECT_ROOT / "data/models/kaggle_price_effect/kaggle_price_effect_model.cbm"
MIN_CONDITION_FACTOR = 0.65


@dataclass(frozen=True, slots=True)
class ConditionAdjustment:
    """Relative adjustment against the same vehicle in a 0 paint / 0 changed state."""

    factor: float
    percent: float
    raw_factor: float
    capped: bool


def build_feature_frame(payload: dict[str, Any]) -> pd.DataFrame:
    """Shape one vehicle into the feature contract used by the condition model."""
    row: dict[str, object] = {}
    for column in CATEGORICAL_FEATURES:
        row[column] = normalize_text(payload.get(column))
    for column in NUMERIC_FEATURES:
        row[column] = pd.to_numeric(payload.get(column), errors="coerce")
    return pd.DataFrame([row], columns=FEATURE_COLUMNS)


@lru_cache(maxsize=2)
def load_price_model(model_path: str):
    """Load the local CatBoost artifact once per API process."""
    try:
        from catboost import CatBoostRegressor
    except ImportError as error:  # pragma: no cover - exercised in the local setup path
        raise RuntimeError("CatBoost kurulu degil. Once requirements.txt dosyasindaki paketleri yukleyin.") from error

    model = CatBoostRegressor()
    model.load_model(model_path)
    return model


def predict_condition_price(payload: dict[str, Any], model_path: Path = DEFAULT_MODEL_PATH) -> float:
    """Predict a historical reference price used only to calculate a relative factor."""
    if not model_path.exists():
        raise FileNotFoundError(f"Model dosyasi bulunamadi: {model_path}")
    model = load_price_model(str(model_path.resolve()))
    predicted_log_price = float(model.predict(build_feature_frame(payload))[0])
    return float(np.expm1(predicted_log_price))


def estimate_condition_adjustment(
    payload: dict[str, Any],
    model_path: Path = DEFAULT_MODEL_PATH,
) -> ConditionAdjustment:
    """Return the paint/change discount relative to a 0 paint / 0 changed reference."""
    required = ("marka", "seri", "model", "yil", "kilometre", "degisen_sayisi", "boyali_sayisi")
    missing = [field for field in required if payload.get(field) is None]
    if missing:
        raise ValueError(f"Durum etkisi icin eksik alanlar: {', '.join(missing)}")

    changed_parts = float(payload["degisen_sayisi"])
    painted_parts = float(payload["boyali_sayisi"])
    if changed_parts < 0 or painted_parts < 0:
        raise ValueError("Boya ve degisen sayisi negatif olamaz.")
    if changed_parts == 0 and painted_parts == 0:
        return ConditionAdjustment(factor=1.0, percent=0.0, raw_factor=1.0, capped=False)

    reference_payload = dict(payload)
    reference_payload["degisen_sayisi"] = 0
    reference_payload["boyali_sayisi"] = 0
    reference_price = predict_condition_price(reference_payload, model_path)
    vehicle_price = predict_condition_price(payload, model_path)
    raw_factor = vehicle_price / reference_price if reference_price > 0 else 1.0
    factor = float(np.clip(raw_factor, MIN_CONDITION_FACTOR, 1.0))
    return ConditionAdjustment(
        factor=factor,
        percent=(factor - 1) * 100,
        raw_factor=raw_factor,
        capped=not np.isclose(factor, raw_factor),
    )


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Kaggle boya ve degisen etkisi modelini test et.")
    parser.add_argument("--brand", required=True, dest="marka")
    parser.add_argument("--series", required=True, dest="seri")
    parser.add_argument("--model", required=True)
    parser.add_argument("--year", required=True, type=int, dest="yil")
    parser.add_argument("--mileage", required=True, type=int, dest="kilometre")
    parser.add_argument("--changed-parts", required=True, type=float, dest="degisen_sayisi")
    parser.add_argument("--painted-parts", required=True, type=float, dest="boyali_sayisi")
    parser.add_argument("--model-path", type=Path, default=DEFAULT_MODEL_PATH)
    args = parser.parse_args(argv)

    adjustment = estimate_condition_adjustment(vars(args), args.model_path)
    print(f"Durum etkisi: %{adjustment.percent:.1f}")
    print(f"Uygulanan katsayi: {adjustment.factor:.3f}")
    if adjustment.capped:
        print("Not: Asiri durum etkisi kullaniciya yanit vermeden once sinirlandi.")


if __name__ == "__main__":
    main()
