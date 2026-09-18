"""调拨路由。"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Batch, Drug, Store, Transfer
from ..schemas import ReceiveIn, TransferIn
from ..services import transfers as transfer_svc

router = APIRouter(prefix="/api/transfers", tags=["transfers"])


@router.post("", status_code=201)
def create_transfer(payload: TransferIn, db: Session = Depends(get_db)):
    t = transfer_svc.create_transfer(
        db, from_store_id=payload.from_store_id, to_store_id=payload.to_store_id,
        batch_id=payload.batch_id, quantity=payload.quantity, operator=payload.operator,
    )
    return {"id": t.id, "transfer_no": t.transfer_no, "status": t.status}


@router.post("/{transfer_id}/receive")
def receive_transfer(transfer_id: int, payload: ReceiveIn, db: Session = Depends(get_db)):
    t = transfer_svc.receive_transfer(db, transfer_id=transfer_id, operator=payload.operator)
    return {"id": t.id, "transfer_no": t.transfer_no, "status": t.status}


@router.get("")
def list_transfers(status: str | None = None, limit: int = 200, db: Session = Depends(get_db)):
    query = db.query(Transfer)
    if status:
        query = query.filter(Transfer.status == status)
    transfers = query.order_by(Transfer.created_at.desc()).limit(limit).all()
    stores = {s.id: s.name for s in db.query(Store).all()}
    batches = {b.id: b for b in db.query(Batch).all()}
    drugs = {d.id: d for d in db.query(Drug).all()}
    result = []
    for t in transfers:
        batch = batches[t.batch_id]
        drug = drugs[batch.drug_id]
        result.append({
            "id": t.id, "transfer_no": t.transfer_no,
            "drug_name": drug.name, "batch_no": batch.batch_no,
            "expiry_date": batch.expiry_date.isoformat(),
            "from_store": stores.get(t.from_store_id, "?"),
            "to_store": stores.get(t.to_store_id, "?"),
            "quantity": t.quantity, "status": t.status,
            "operator": t.operator,
            "created_at": t.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "received_at": t.received_at.strftime("%Y-%m-%d %H:%M:%S") if t.received_at else None,
            "received_by": t.received_by,
        })
    return result
