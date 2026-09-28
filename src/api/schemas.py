"""Pydantic response contracts for the public API."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class ApiMessage(BaseModel):
    message: str


class CatalogOption(BaseModel):
    name: str
    listing_count: int | None = None


class CatalogResponse(BaseModel):
    items: list[CatalogOption]


class HealthResponse(BaseModel):
    status: str
    database_available: bool
    table: str | None = None
    listing_count: int | None = None
    message: str | None = None
    # Data-flow freshness. Null values mean the pipeline has not recorded a
    # successful run yet, which is reported as-is rather than guessed.
    last_pipeline_success_at: str | None = None
    pipeline_age_hours: float | None = None
    pipeline_stale: bool | None = None
    # Where the analysed listings come from. "demo" means synthetic data.
    data_sources: list[str] = []
    demo_data: bool = False


class MarketOverview(BaseModel):
    median_price: float | None = None
    average_price: float | None = None
    listing_count: int = 0
    last_updated_at: str | None = None
    source_status: str
    change_30d: float | None = None
    change_90d: float | None = None
    change_yoy: float | None = None
    message: str | None = None


class TrendPoint(BaseModel):
    date: date
    median_price: float
    average_price: float
    listing_count: int
    clean_median_price: float | None = None
    clean_average_price: float | None = None
    clean_listing_count: int | None = None


class TrendResponse(BaseModel):
    available: bool
    label: str = "İlan tarihine göre medyan fiyat"
    points: list[TrendPoint] = Field(default_factory=list)
    clean_available: bool = False
    clean_listing_count: int = 0
    message: str | None = None


class PriceRelationshipPoint(BaseModel):
    label: str
    median_price: float
    average_price: float
    listing_count: int


class PriceRelationshipsResponse(BaseModel):
    listing_count: int = 0
    clean_listing_count: int = 0
    year_available: bool = False
    mileage_available: bool = False
    clean_year_available: bool = False
    clean_mileage_available: bool = False
    year_points: list[PriceRelationshipPoint] = Field(default_factory=list)
    mileage_points: list[PriceRelationshipPoint] = Field(default_factory=list)
    clean_year_points: list[PriceRelationshipPoint] = Field(default_factory=list)
    clean_mileage_points: list[PriceRelationshipPoint] = Field(default_factory=list)
    message: str | None = None


class MarketTableRow(BaseModel):
    label: str
    average_price: float
    median_price: float
    listing_count: int
    change_30d: float | None = None
    change_90d: float | None = None
    change_yoy: float | None = None


class MarketTableResponse(BaseModel):
    group_by: str
    rows: list[MarketTableRow]
    message: str | None = None


class MoverItem(BaseModel):
    label: str
    change_percent: float
    average_price: float
    listing_count: int
    direction: str


class MoversResponse(BaseModel):
    available: bool
    items: list[MoverItem] = Field(default_factory=list)
    message: str | None = None


class SimilarListing(BaseModel):
    id: int | None = None
    title: str
    brand: str | None = None
    series: str | None = None
    model: str | None = None
    year: int | None = None
    mileage_km: int | None = None
    price: float
    city: str | None = None
    listing_date: str | None = None
    listing_url: str | None = None
    similarity_score: float | None = None


class ComparisonSummary(BaseModel):
    matched_listing_count: int = 0
    selected_listing_count: int = 0
    used_listing_count: int
    outlier_count: int = 0
    selection_mode: str = "all_matching"
    selection_note: str
    clean_only: bool = False
    median_year: int | None = None
    median_mileage_km: int | None = None


class ReferencePricePoint(BaseModel):
    price: float
    year: int | None = None
    mileage_km: int | None = None


class ReferenceMileagePoint(BaseModel):
    lower_mileage_km: int
    upper_mileage_km: int
    median_price: float
    average_price: float
    listing_count: int


class ValuationRequest(BaseModel):
    brand: str | None = Field(default=None, max_length=80)
    series: str | None = Field(default=None, max_length=100)
    model: str | None = Field(default=None, max_length=140)
    body_type: str | None = Field(default=None, max_length=60)
    fuel_type: str | None = Field(default=None, max_length=60)
    transmission: str | None = Field(default=None, max_length=60)
    year: int | None = Field(default=None, ge=1900, le=2100)
    mileage_km: int | None = Field(default=None, ge=0, le=2_000_000)
    asking_price: int | None = Field(default=None, ge=1)
    clean_only: bool = False
    changed_parts: int | None = Field(default=None, ge=0, le=30)
    painted_parts: int | None = Field(default=None, ge=0, le=30)


class ValuationResponse(BaseModel):
    status: str
    estimated_market_value: float | None = None
    recommended_low_price: float | None = None
    recommended_high_price: float | None = None
    median_price: float | None = None
    listing_count: int = 0
    confidence: str | None = None
    price_assessment: str | None = None
    asking_price_delta_percent: float | None = None
    asking_price: float | None = None
    explanation: str
    comparison_summary: ComparisonSummary | None = None
    reference_price_points: list[ReferencePricePoint] = Field(default_factory=list)
    reference_mileage_points: list[ReferenceMileagePoint] = Field(default_factory=list)
    reference_listing_trend: list[TrendPoint] = Field(default_factory=list)
    condition_adjustment_percent: float | None = None
    condition_adjustment_note: str | None = None


class SimilarListingsResponse(BaseModel):
    items: list[SimilarListing] = Field(default_factory=list)
    message: str | None = None
