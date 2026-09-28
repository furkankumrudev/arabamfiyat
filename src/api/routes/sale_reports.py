"""Users report what their car actually sold for."""

from __future__ import annotations

from fastapi import APIRouter

from ..schemas import SaleReportRequest, SaleReportResponse
from ..services.sale_reports import save_report
from ..settings import sale_reports_db_path

router = APIRouter(prefix="/api", tags=["sale-reports"])


@router.post("/sale-reports", response_model=SaleReportResponse, status_code=201)
def create_sale_report(report: SaleReportRequest) -> SaleReportResponse:
    save_report(sale_reports_db_path(), report.model_dump())
    return SaleReportResponse(status="saved", message="Teşekkürler, satış bilginiz kaydedildi.")
