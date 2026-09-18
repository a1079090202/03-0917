"""业务操作路由：入库、出库、调拨、质检、召回、报表。

业务层 BizError 统一映射 400，前端直接弹 detail。
"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas import (
    HoldIn,
    InboundIn,
    OutboundIn,
    PreviewIn,
    RecallIn,
    ReleaseIn,
    TransferReceiveIn,
    TransferShipIn,
)
from ..services import inventory, recall as recall_svc, reports as report_svc

router = APIRouter(prefix="/api", tags=["业务操作"])


# ---------------------------------------------------------------- 入库

@router.post("/inbound")
def inbound(payload: InboundIn, db: Session = Depends(get_db)):
    try:
        return inventory.create_inbound(
            db, drug_id=payload.drug_id, batch_no=payload.batch_no,
            production_date=payload.production_date, expiry_date=payload.expiry_date,
            qty=payload.qty, supplier=payload.supplier,
            operator=payload.operator, note=payload.note,
        )
    except inventory.BizError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------- 出库

@router.post("/outbound/preview")
def outbound_preview(payload: PreviewIn, db: Session = Depends(get_db)):
    try:
        return inventory.fefo_preview(
            db, drug_id=payload.drug_id, location_id=payload.location_id, qty=payload.qty
        )
    except inventory.BizError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/outbound")
def outbound(payload: OutboundIn, db: Session = Depends(get_db)):
    try:
        return inventory.create_outbound(
            db, drug_id=payload.drug_id, location_id=payload.location_id,
            qty=payload.qty, kind=payload.kind, operator=payload.operator,
            note=payload.note, requested_batch_id=payload.requested_batch_id,
        )
    except inventory.BizError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------- 调拨

@router.post("/transfers")
def transfer_ship(payload: TransferShipIn, db: Session = Depends(get_db)):
    try:
        return inventory.ship_transfer(
            db, drug_id=payload.drug_id,
            from_location_id=payload.from_location_id,
            to_location_id=payload.to_location_id, qty=payload.qty,
            operator=payload.operator,
        )
    except inventory.BizError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/transfers/{transfer_id}/receive")
def transfer_receive(transfer_id: int, payload: TransferReceiveIn,
                     db: Session = Depends(get_db)):
    try:
        return inventory.receive_transfer(
            db, transfer_id=transfer_id, operator=payload.operator
        )
    except inventory.BizError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------- 质检

@router.post("/quality/hold")
def quality_hold(payload: HoldIn, db: Session = Depends(get_db)):
    try:
        return inventory.quality_hold(
            db, batch_id=payload.batch_id, reason=payload.reason,
            operator=payload.operator,
        )
    except inventory.BizError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/quality/release")
def quality_release(payload: ReleaseIn, db: Session = Depends(get_db)):
    try:
        return inventory.quality_release(
            db, batch_id=payload.batch_id, doc_no=payload.doc_no,
            reason=payload.reason, operator=payload.operator,
        )
    except inventory.BizError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------- 召回

@router.post("/recalls")
def recall_register(payload: RecallIn, db: Session = Depends(get_db)):
    try:
        return recall_svc.register_recall(
            db, batch_id=payload.batch_id, no=payload.no, issuer=payload.issuer,
            issued_date=payload.issued_date, note=payload.note,
        )
    except recall_svc.BizError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/recalls/trace")
def recall_trace(batch_no: str, drug_id: int | None = None,
                 db: Session = Depends(get_db)):
    try:
        return recall_svc.trace_by_batch(db, batch_no=batch_no, drug_id=drug_id)
    except recall_svc.BizError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ---------------------------------------------------------------- 报表

@router.get("/reports/monthly")
def monthly_report(year: int | None = None, month: int | None = None,
                   db: Session = Depends(get_db)):
    today = date.today()
    if year is None or month is None:
        # 默认上月：1 号看的正是上个月
        first_of_this = today.replace(day=1)
        y, m = (today.year - 1, 12) if today.month == 1 else (today.year, today.month - 1)
        year, month = y, m
    if not 1 <= month <= 12:
        raise HTTPException(status_code=400, detail="月份必须在 1~12 之间")
    return report_svc.monthly_report(db, year, month)
