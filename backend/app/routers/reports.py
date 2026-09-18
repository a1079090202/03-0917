"""报表路由：月度批次流向表 + 近效期清单。"""
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..services import reports as reports_svc

router = APIRouter(prefix="/api/reports", tags=["reports"])


def _default_month() -> str:
    """默认上月（每月 1 号看上月）。"""
    today = date.today()
    y, m = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
    return f"{y:04d}-{m:02d}"


@router.get("/monthly-flow")
def monthly_flow(month: str = Query(default_factory=_default_month),
                 db: Session = Depends(get_db)):
    return reports_svc.monthly_flow(db, month)


@router.get("/near-expiry")
def near_expiry(month: str = Query(default_factory=_default_month),
                db: Session = Depends(get_db)):
    return reports_svc.near_expiry_report(db, month)
