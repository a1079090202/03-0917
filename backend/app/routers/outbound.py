"""出库路由（含 FEFO 预览）。"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Batch, Drug, OutboundItem, OutboundOrder
from ..schemas import OutboundIn, PreviewIn
from ..services import outbound as outbound_svc

router = APIRouter(prefix="/api/outbound", tags=["outbound"])


@router.post("", status_code=201)
def create_outbound(payload: OutboundIn, db: Session = Depends(get_db)):
    order = outbound_svc.create_outbound(
        db, store_id=payload.store_id, order_type=payload.order_type,
        operator=payload.operator, items=payload.items,
    )
    items = (db.query(OutboundItem, Batch)
             .join(Batch, OutboundItem.batch_id == Batch.id)
             .filter(OutboundItem.order_id == order.id).all())
    return {
        "id": order.id,
        "order_no": order.order_no,
        "items": [{"batch_no": b.batch_no, "expiry_date": b.expiry_date.isoformat(),
                   "quantity": it.quantity} for it, b in items],
    }


@router.post("/preview")
def preview_outbound(payload: PreviewIn, db: Session = Depends(get_db)):
    return outbound_svc.preview_outbound(
        db, store_id=payload.store_id, drug_id=payload.drug_id, quantity=payload.quantity,
    )


@router.get("")
def list_outbound(limit: int = 100, db: Session = Depends(get_db)):
    orders = (db.query(OutboundOrder).order_by(OutboundOrder.created_at.desc())
              .limit(limit).all())
    result = []
    for o in orders:
        items = (db.query(OutboundItem, Batch, Drug)
                 .join(Batch, OutboundItem.batch_id == Batch.id)
                 .join(Drug, Batch.drug_id == Drug.id)
                 .filter(OutboundItem.order_id == o.id).all())
        result.append({
            "id": o.id, "order_no": o.order_no, "store_id": o.store_id,
            "order_type": o.order_type, "operator": o.operator,
            "created_at": o.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "items": [{
                "drug_name": d.name, "batch_no": b.batch_no,
                "expiry_date": b.expiry_date.isoformat(), "quantity": it.quantity,
            } for it, b, d in items],
        })
    return result
