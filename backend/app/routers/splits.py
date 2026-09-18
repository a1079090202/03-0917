"""拆零台账路由。"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Batch, Drug, SplitRecord, Store

router = APIRouter(prefix="/api/split-records", tags=["splits"])


@router.get("")
def list_split_records(store_id: int | None = None, limit: int = 200,
                       db: Session = Depends(get_db)):
    query = (db.query(SplitRecord, Batch, Drug, Store)
             .join(Batch, SplitRecord.batch_id == Batch.id)
             .join(Drug, SplitRecord.drug_id == Drug.id)
             .join(Store, SplitRecord.store_id == Store.id))
    if store_id:
        query = query.filter(SplitRecord.store_id == store_id)
    rows = query.order_by(SplitRecord.ts.desc()).limit(limit).all()
    return [{
        "id": r.id, "ts": r.ts.strftime("%Y-%m-%d %H:%M:%S"),
        "store_name": s.name, "drug_name": d.name, "spec": d.spec, "unit": d.unit,
        "batch_no": b.batch_no, "expiry_date": b.expiry_date.isoformat(),
        "quantity": r.quantity, "operator": r.operator,
        "outbound_order_id": r.outbound_order_id,
    } for r, b, d, s in rows]
