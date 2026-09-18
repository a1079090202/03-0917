"""入库路由。"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (Batch, Drug, InboundItem, InboundOrder)
from ..schemas import InboundIn
from ..services import inbound as inbound_svc

router = APIRouter(prefix="/api/inbound", tags=["inbound"])


@router.post("", status_code=201)
def create_inbound(payload: InboundIn, db: Session = Depends(get_db)):
    order = inbound_svc.create_inbound(
        db, store_id=payload.store_id, operator=payload.operator,
        items=payload.items, note=payload.note,
    )
    return {"id": order.id, "order_no": order.order_no}


@router.get("")
def list_inbound(limit: int = 100, db: Session = Depends(get_db)):
    orders = (db.query(InboundOrder).order_by(InboundOrder.created_at.desc())
              .limit(limit).all())
    result = []
    for o in orders:
        items = (db.query(InboundItem, Batch, Drug)
                 .join(Batch, InboundItem.batch_id == Batch.id)
                 .join(Drug, Batch.drug_id == Drug.id)
                 .filter(InboundItem.order_id == o.id).all())
        result.append({
            "id": o.id, "order_no": o.order_no, "store_id": o.store_id,
            "operator": o.operator, "created_at": o.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "items": [{
                "drug_name": d.name, "batch_no": b.batch_no,
                "expiry_date": b.expiry_date.isoformat(),
                "quantity": it.quantity, "supplier": it.supplier,
            } for it, b, d in items],
        })
    return result
