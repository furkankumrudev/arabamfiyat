"""Catalog endpoints sourced from the shipped catalog and real database.

Only brand, series and model are served. Body type, fuel type and transmission
are not present on the search-result rows the ingestion layer reads, so an
endpoint for them would always answer with an empty list.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query

from ..database import ListingRepository
from ..dependencies import safe_repository
from ..schemas import CatalogOption, CatalogResponse
from ..settings import PROJECT_ROOT

router = APIRouter(prefix="/api/catalog", tags=["catalog"])
CATALOG_PATH = PROJECT_ROOT / "data" / "reference" / "vehicle_catalog.json"


def load_catalog() -> dict[str, object]:
    if not CATALOG_PATH.exists():
        return {"brands": []}
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def unique(values: list[str]) -> list[str]:
    return sorted({value.strip() for value in values if value and value.strip()})


@router.get("/brands", response_model=CatalogResponse)
def brands(repository: ListingRepository = Depends(safe_repository)) -> CatalogResponse:
    catalog = load_catalog()
    catalog_names = [str(item.get("name")) for item in catalog.get("brands", []) if isinstance(item, dict) and item.get("name")]
    db_names = repository.distinct_values("brand")
    counts = repository.load_listings().groupby("brand").size().to_dict()
    return CatalogResponse(items=[CatalogOption(name=name, listing_count=int(counts.get(name, 0))) for name in unique(catalog_names + db_names)])


@router.get("/series", response_model=CatalogResponse)
def series(brand: str = Query(..., min_length=1), repository: ListingRepository = Depends(safe_repository)) -> CatalogResponse:
    catalog = load_catalog()
    catalog_names: list[str] = []
    for item in catalog.get("brands", []):
        if isinstance(item, dict) and str(item.get("name", "")).casefold() == brand.casefold():
            catalog_names = [str(series.get("name")) for series in item.get("series", []) if isinstance(series, dict) and series.get("name")]
            break
    db_names = repository.distinct_values("series", {"brand": brand})
    counts = repository.load_listings({"brand": brand}).groupby("series").size().to_dict()
    return CatalogResponse(items=[CatalogOption(name=name, listing_count=int(counts.get(name, 0))) for name in unique(catalog_names + db_names)])


@router.get("/models", response_model=CatalogResponse)
def models(
    brand: str = Query(..., min_length=1), series: str = Query(..., min_length=1),
    repository: ListingRepository = Depends(safe_repository),
) -> CatalogResponse:
    catalog = load_catalog()
    catalog_names: list[str] = []
    for item in catalog.get("brands", []):
        if not isinstance(item, dict) or str(item.get("name", "")).casefold() != brand.casefold():
            continue
        for catalog_series in item.get("series", []):
            if isinstance(catalog_series, dict) and str(catalog_series.get("name", "")).casefold() == series.casefold():
                catalog_names = [str(model) for model in catalog_series.get("models", []) if model]
                break
    db_filters = {"brand": brand, "series": series}
    db_names = repository.distinct_values("model", db_filters)
    counts = repository.load_listings(db_filters).groupby("model").size().to_dict()
    return CatalogResponse(items=[CatalogOption(name=name, listing_count=int(counts.get(name, 0))) for name in unique(catalog_names + db_names)])

