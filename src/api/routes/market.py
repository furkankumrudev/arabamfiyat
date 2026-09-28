"""Public market overview, trend, table and movement routes."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query

from ..database import ListingRepository
from ..dependencies import MarketFilters, safe_repository
from ..schemas import MarketOverview, MarketTableResponse, MoversResponse, PriceRelationshipsResponse, TrendResponse
from ..services.market_service import grouped_table, movers, overview, price_relationships
from ..services.trend_service import build_listing_trend, merge_clean_trend

router = APIRouter(prefix="/api/market", tags=["market"])


@router.get("/overview", response_model=MarketOverview)
def get_overview(filters: MarketFilters = Depends(), repository: ListingRepository = Depends(safe_repository)) -> MarketOverview:
    return MarketOverview(**overview(repository, filters.as_dict()))


@router.get("/trend", response_model=TrendResponse)
def get_trend(
    filters: MarketFilters = Depends(), start_date: date | None = None, end_date: date | None = None,
    repository: ListingRepository = Depends(safe_repository),
    interval: str = Query(default="day", pattern="^(day|week)$"),
) -> TrendResponse:
    if start_date and end_date and start_date > end_date:
        return TrendResponse(available=False, message="Başlangıç tarihi bitiş tarihinden büyük olamaz.")
    listings = repository.load_listings(filters.as_dict())
    points = build_listing_trend(listings, start_date, end_date, interval)
    if len(points) < 2:
        return TrendResponse(available=False, message="Bu dönem için yeterli geçmiş veri bulunmuyor.")
    clean_listings = listings[listings["is_clean_claimed"].fillna(0).astype(int) == 1] if "is_clean_claimed" in listings else listings.iloc[0:0]
    clean_points = build_listing_trend(clean_listings, start_date, end_date, interval)
    return TrendResponse(
        available=True,
        points=merge_clean_trend(points, clean_points),
        clean_available=len(clean_points) >= 2,
        clean_listing_count=int(len(clean_listings)),
    )


@router.get("/price-relationships", response_model=PriceRelationshipsResponse)
def get_price_relationships(
    filters: MarketFilters = Depends(), repository: ListingRepository = Depends(safe_repository),
) -> PriceRelationshipsResponse:
    return PriceRelationshipsResponse(**price_relationships(repository, filters.as_dict()))


@router.get("/table", response_model=MarketTableResponse)
def get_table(
    filters: MarketFilters = Depends(), group_by: str = Query(default="brand", pattern="^(brand|body_type|fuel_type)$"),
    repository: ListingRepository = Depends(safe_repository),
) -> MarketTableResponse:
    rows = grouped_table(repository, filters.as_dict(), group_by)
    return MarketTableResponse(group_by=group_by, rows=rows, message=None if rows else "Seçilen filtreler için tablo verisi yok.")


@router.get("/movers", response_model=MoversResponse)
def get_movers(
    direction: str = Query(default="down", pattern="^(up|down)$"), repository: ListingRepository = Depends(safe_repository),
) -> MoversResponse:
    items = movers(repository, direction)
    return MoversResponse(
        available=bool(items), items=items,
        message=None if items else "Hareket hesaplamak için en az iki gerçek günlük piyasa özeti gerekir.",
    )
