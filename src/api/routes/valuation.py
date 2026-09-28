"""Valuation endpoint backed by the existing market-analysis engine."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..database import ListingRepository
from ..dependencies import safe_repository
from ..schemas import ValuationRequest, ValuationResponse
from ..services.market_service import valuation
from ..services.sale_reports import summarize_reports
from ..settings import sale_reports_db_path

router = APIRouter(prefix="/api", tags=["valuation"])


@router.post("/valuation", response_model=ValuationResponse)
def create_valuation(payload: ValuationRequest, repository: ListingRepository = Depends(safe_repository)) -> ValuationResponse:
    result = valuation(repository, payload.model_dump())
    result["sale_reports"] = summarize_reports(sale_reports_db_path(), payload.brand, payload.series, payload.year)
    return ValuationResponse(**result)
