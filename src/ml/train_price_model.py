"""Train the Kaggle condition-effect model without using old TL prices as live pricing."""

from __future__ import annotations

import argparse
import json
import math
import unicodedata
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split

TARGET_COLUMN = "fiyat"
CATEGORICAL_FEATURES = (
    "marka",
    "seri",
    "model",
)
NUMERIC_FEATURES = (
    "yil",
    "kilometre",
    "degisen_sayisi",
    "boyali_sayisi",
)
FEATURE_COLUMNS = (*CATEGORICAL_FEATURES, *NUMERIC_FEATURES)
REQUIRED_COLUMNS = (*FEATURE_COLUMNS, TARGET_COLUMN)


@dataclass(frozen=True, slots=True)
class TrainingConfig:
    """Reproducible settings for the first price-effect model."""

    random_seed: int = 42
    test_size: float = 0.20
    iterations: int = 900
    learning_rate: float = 0.045
    depth: int = 8
    early_stopping_rounds: int = 80
    min_year: int = 1980
    max_year: int = 2025
    max_mileage: int = 750_000
    min_price: int = 50_000
    max_price: int = 50_000_000
    max_condition_parts: int = 30
    group_outlier_min_records: int = 8
    group_outlier_iqr_multiplier: float = 3.0


@dataclass(frozen=True, slots=True)
class CleaningReport:
    raw_rows: int
    valid_core_rows: int
    rows_after_hard_limits: int
    rows_after_group_outliers: int
    removed_missing_core: int
    removed_hard_limits: int
    removed_group_outliers: int


def normalize_text(value: object) -> str:
    """Normalize categorical values without turning missing values into a real vehicle category."""
    if pd.isna(value):
        return "Bilinmiyor"
    text = unicodedata.normalize("NFKC", str(value)).strip()
    text = text.replace("ţ", "ş").replace("Ţ", "Ş")
    return " ".join(text.split()) or "Bilinmiyor"


def _remove_group_price_outliers(frame: pd.DataFrame, config: TrainingConfig) -> pd.DataFrame:
    """Drop implausible prices only when a sufficiently large peer group proves they are anomalous."""
    grouped = frame.groupby(["marka", "seri", "model"], observed=True)[TARGET_COLUMN]
    stats = grouped.agg(["count", "median", lambda values: values.quantile(0.25), lambda values: values.quantile(0.75)])
    stats.columns = ["group_count", "group_median", "q1", "q3"]
    stats["iqr"] = stats["q3"] - stats["q1"]

    enriched = frame.join(stats, on=["marka", "seri", "model"])
    usable_group = (enriched["group_count"] >= config.group_outlier_min_records) & (enriched["iqr"] > 0)
    lower = enriched["q1"] - config.group_outlier_iqr_multiplier * enriched["iqr"]
    upper = enriched["q3"] + config.group_outlier_iqr_multiplier * enriched["iqr"]
    is_outlier = usable_group & ~enriched[TARGET_COLUMN].between(lower, upper)
    return enriched.loc[~is_outlier, frame.columns].copy()


def prepare_training_frame(raw: pd.DataFrame, config: TrainingConfig | None = None) -> tuple[pd.DataFrame, CleaningReport]:
    """Create a frame for learning paint/change effects within comparable vehicles."""
    config = config or TrainingConfig()
    missing_columns = set(REQUIRED_COLUMNS).difference(raw.columns)
    if missing_columns:
        raise ValueError(f"Egitim verisinde zorunlu sutunlar eksik: {sorted(missing_columns)}")

    frame = raw.copy()
    for column in CATEGORICAL_FEATURES:
        if column not in frame:
            frame[column] = "Bilinmiyor"
        frame[column] = frame[column].map(normalize_text)

    for column in (*NUMERIC_FEATURES, TARGET_COLUMN):
        if column not in frame:
            frame[column] = np.nan
        frame[column] = pd.to_numeric(frame[column], errors="coerce")

    raw_rows = len(frame)
    frame = frame.dropna(subset=list(REQUIRED_COLUMNS)).copy()
    valid_core_rows = len(frame)
    frame = frame[
        frame["yil"].between(config.min_year, config.max_year)
        & frame["kilometre"].between(0, config.max_mileage)
        & frame[TARGET_COLUMN].between(config.min_price, config.max_price)
        & frame["degisen_sayisi"].between(0, config.max_condition_parts)
        & frame["boyali_sayisi"].between(0, config.max_condition_parts)
    ].copy()
    rows_after_hard_limits = len(frame)

    frame = _remove_group_price_outliers(frame, config)
    rows_after_group_outliers = len(frame)

    for column in NUMERIC_FEATURES:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")

    report = CleaningReport(
        raw_rows=raw_rows,
        valid_core_rows=valid_core_rows,
        rows_after_hard_limits=rows_after_hard_limits,
        rows_after_group_outliers=rows_after_group_outliers,
        removed_missing_core=raw_rows - valid_core_rows,
        removed_hard_limits=valid_core_rows - rows_after_hard_limits,
        removed_group_outliers=rows_after_hard_limits - rows_after_group_outliers,
    )
    return frame.loc[:, [*FEATURE_COLUMNS, TARGET_COLUMN]].reset_index(drop=True), report


def _price_strata(prices: pd.Series) -> pd.Series | None:
    """Use robust price bands for a balanced holdout split when possible."""
    try:
        bands = pd.qcut(np.log1p(prices), q=10, duplicates="drop")
    except ValueError:
        return None
    counts = bands.value_counts()
    return bands if not counts.empty and counts.min() >= 2 else None


def _metrics(actual: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    error = np.abs(actual - predicted)
    denominator = np.maximum((np.abs(actual) + np.abs(predicted)) / 2, 1)
    return {
        "mae_tl": float(mean_absolute_error(actual, predicted)),
        "median_absolute_error_tl": float(np.median(error)),
        "rmse_tl": float(math.sqrt(mean_squared_error(actual, predicted))),
        "r2": float(r2_score(actual, predicted)),
        "smape_percent": float(np.mean(error / denominator) * 100),
        "within_10_percent": float(np.mean(error / np.maximum(actual, 1) <= 0.10) * 100),
        "within_20_percent": float(np.mean(error / np.maximum(actual, 1) <= 0.20) * 100),
    }


def train_model(
    data_path: Path,
    output_dir: Path,
    config: TrainingConfig | None = None,
) -> dict[str, object]:
    """Train CatBoost to estimate relative paint/change effects for comparable cars."""
    try:
        from catboost import CatBoostRegressor
    except ImportError as error:  # pragma: no cover - exercised in the local setup path
        raise RuntimeError("CatBoost kurulu degil. Once requirements.txt dosyasindaki paketleri yukleyin.") from error

    config = config or TrainingConfig()
    raw = pd.read_csv(data_path)
    frame, cleaning = prepare_training_frame(raw, config)
    features = frame.loc[:, FEATURE_COLUMNS].copy()
    target_log = np.log1p(frame[TARGET_COLUMN])
    train_features, test_features, train_target, test_target = train_test_split(
        features,
        target_log,
        test_size=config.test_size,
        random_state=config.random_seed,
        stratify=_price_strata(frame[TARGET_COLUMN]),
    )

    model = CatBoostRegressor(
        loss_function="RMSE",
        eval_metric="RMSE",
        iterations=config.iterations,
        learning_rate=config.learning_rate,
        depth=config.depth,
        random_seed=config.random_seed,
        l2_leaf_reg=5,
        random_strength=0.5,
        verbose=False,
        allow_writing_files=False,
    )
    model.fit(
        train_features,
        train_target,
        cat_features=list(CATEGORICAL_FEATURES),
        eval_set=(test_features, test_target),
        early_stopping_rounds=config.early_stopping_rounds,
        verbose=False,
    )

    predicted = np.expm1(model.predict(test_features))
    actual = np.expm1(test_target.to_numpy())
    feature_importance = sorted(
        (
            {"feature": feature, "importance": float(importance)}
            for feature, importance in zip(FEATURE_COLUMNS, model.get_feature_importance(), strict=True)
        ),
        key=lambda item: item["importance"],
        reverse=True,
    )
    result: dict[str, object] = {
        "data_path": str(data_path),
        "training_rows": int(len(train_features)),
        "test_rows": int(len(test_features)),
        "features": list(FEATURE_COLUMNS),
        "cleaning": asdict(cleaning),
        "metrics": _metrics(actual, predicted),
        "feature_importance": feature_importance,
        "best_iteration": int(model.get_best_iteration()),
        "config": asdict(config),
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    model.save_model(str(output_dir / "kaggle_price_effect_model.cbm"))
    (output_dir / "kaggle_price_effect_metrics.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return result


def _format_metrics(result: dict[str, object]) -> str:
    metrics = result["metrics"]
    assert isinstance(metrics, dict)
    return "\n".join([
        f"Egitim satiri: {result['training_rows']:,}",
        f"Test satiri: {result['test_rows']:,}",
        f"MAE: {metrics['mae_tl']:,.0f} TL",
        f"Medyan mutlak hata: {metrics['median_absolute_error_tl']:,.0f} TL",
        f"SMAPE: %{metrics['smape_percent']:.2f}",
        f"%10 icinde tahmin: %{metrics['within_10_percent']:.2f}",
        f"%20 icinde tahmin: %{metrics['within_20_percent']:.2f}",
        f"R2: {metrics['r2']:.4f}",
    ])


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Kaggle boya ve degisen etkisi modelini egit.")
    parser.add_argument("--data", type=Path, default=Path("car_price_prediction.csv"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/models/kaggle_price_effect"))
    parser.add_argument("--iterations", type=int, default=TrainingConfig().iterations)
    args = parser.parse_args(argv)
    config = TrainingConfig(iterations=args.iterations)
    result = train_model(args.data, args.output_dir, config)
    print(_format_metrics(result))
    print(f"Model: {args.output_dir / 'kaggle_price_effect_model.cbm'}")
    print(f"Rapor: {args.output_dir / 'kaggle_price_effect_metrics.json'}")


if __name__ == "__main__":
    main()
