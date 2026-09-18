"""基础数据与台账查询：药品、门店、批次台账、库存、流水、仪表盘。"""
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (Batch, BatchStatus, Drug, Inventory, QCRecord, Store,
                      StockLedger, Transfer, TransferStatus)
from ..schemas import DrugIn
from ..services.common import BizError
from ..services.expiry_lock import (apply_expiry_locks, is_expired,
                                    is_near_expiry)

router = APIRouter(prefix="/api", tags=["catalog"])


@router.get("/drugs")
def list_drugs(db: Session = Depends(get_db)):
    drugs = db.query(Drug).order_by(Drug.code).all()
    return [{"id": d.id, "code": d.code, "name": d.name, "spec": d.spec,
             "unit": d.unit, "manufacturer": d.manufacturer} for d in drugs]


@router.post("/drugs", status_code=201)
def create_drug(payload: DrugIn, db: Session = Depends(get_db)):
    if db.query(Drug).filter(Drug.code == payload.code).first():
        raise BizError(f"药品编码 {payload.code} 已存在", 409)
    d = Drug(**payload.model_dump())
    db.add(d)
    db.commit()
    db.refresh(d)
    return {"id": d.id, "code": d.code, "name": d.name}


@router.get("/stores")
def list_stores(db: Session = Depends(get_db)):
    stores = db.query(Store).order_by(Store.id).all()
    return [{"id": s.id, "code": s.code, "name": s.name, "is_warehouse": s.is_warehouse}
            for s in stores]


@router.get("/batches")
def list_batches(status: str | None = None, drug_id: int | None = None,
                 q: str | None = None, db: Session = Depends(get_db)):
    """批次台账：状态、近效期标记、剩余天数、全连锁在手量。"""
    apply_expiry_locks(db, date.today())
    db.commit()
    today = date.today()

    query = db.query(Batch, Drug).join(Drug, Batch.drug_id == Drug.id)
    if status:
        query = query.filter(Batch.status == status)
    if drug_id:
        query = query.filter(Batch.drug_id == drug_id)
    if q:
        like = f"%{q}%"
        query = query.filter((Batch.batch_no.like(like)) | (Drug.name.like(like)))
    rows = query.order_by(Batch.expiry_date.asc()).all()

    on_hand = dict(db.query(Inventory.batch_id, func.sum(Inventory.quantity))
                   .group_by(Inventory.batch_id).all())
    result = []
    for batch, drug in rows:
        expired = is_expired(batch, today)
        result.append({
            "id": batch.id,
            "drug_id": drug.id,
            "drug_name": drug.name,
            "spec": drug.spec,
            "unit": drug.unit,
            "batch_no": batch.batch_no,
            "production_date": batch.production_date.isoformat(),
            "expiry_date": batch.expiry_date.isoformat(),
            "supplier": batch.supplier,
            "status": batch.status,
            "is_near_expiry": is_near_expiry(batch, today),
            "is_expired": expired,
            "days_to_expiry": (batch.expiry_date - today).days,
            "on_hand": int(on_hand.get(batch.id, 0) or 0),
            "qc_reason": batch.qc_reason,
            "qc_release_no": batch.qc_release_no,
        })
    return result


@router.get("/inventory")
def list_inventory(store_id: int | None = None, drug_id: int | None = None,
                   include_zero: bool = False, db: Session = Depends(get_db)):
    apply_expiry_locks(db, date.today())
    db.commit()
    today = date.today()
    query = (db.query(Inventory, Batch, Drug, Store)
             .join(Batch, Inventory.batch_id == Batch.id)
             .join(Drug, Batch.drug_id == Drug.id)
             .join(Store, Inventory.store_id == Store.id))
    if store_id:
        query = query.filter(Inventory.store_id == store_id)
    if drug_id:
        query = query.filter(Batch.drug_id == drug_id)
    if not include_zero:
        query = query.filter(Inventory.quantity > 0)
    rows = query.order_by(Store.id, Drug.name, Batch.expiry_date).all()
    return [{
        "store_id": store.id, "store_name": store.name,
        "drug_id": drug.id, "drug_name": drug.name, "spec": drug.spec, "unit": drug.unit,
        "batch_id": batch.id, "batch_no": batch.batch_no,
        "expiry_date": batch.expiry_date.isoformat(),
        "status": batch.status,
        "is_near_expiry": is_near_expiry(batch, today),
        "is_expired": is_expired(batch, today),
        "quantity": inv.quantity,
    } for inv, batch, drug, store in rows]


@router.get("/drugs/{drug_id}/sellable-batches")
def sellable_batches(drug_id: int, store_id: int = Query(...), db: Session = Depends(get_db)):
    """某店某药当前可售批次（效期升序），供出库页手工指定与预览。"""
    apply_expiry_locks(db, date.today())
    db.commit()
    today = date.today()
    rows = (db.query(Inventory, Batch)
            .join(Batch, Inventory.batch_id == Batch.id)
            .filter(Inventory.store_id == store_id, Batch.drug_id == drug_id,
                    Inventory.quantity > 0)
            .order_by(Batch.expiry_date.asc(), Batch.id.asc()).all())
    result = []
    for inv, batch in rows:
        sellable = (batch.status == BatchStatus.NORMAL and batch.expiry_date >= today)
        result.append({
            "batch_id": batch.id, "batch_no": batch.batch_no,
            "expiry_date": batch.expiry_date.isoformat(),
            "available": inv.quantity, "status": batch.status,
            "sellable": sellable,
            "block_reason": (
                "已过期锁死" if batch.status == BatchStatus.EXPIRED_LOCKED
                else "质检停售中" if batch.status == BatchStatus.QC_SUSPENDED
                else ""
            ),
        })
    return result


@router.get("/ledger")
def list_ledger(batch_id: int | None = None, store_id: int | None = None,
                change_type: str | None = None, limit: int = Query(200, le=1000),
                db: Session = Depends(get_db)):
    query = (db.query(StockLedger, Batch, Drug, Store)
             .join(Batch, StockLedger.batch_id == Batch.id)
             .join(Drug, Batch.drug_id == Drug.id)
             .outerjoin(Store, StockLedger.store_id == Store.id))
    if batch_id:
        query = query.filter(StockLedger.batch_id == batch_id)
    if store_id:
        query = query.filter(StockLedger.store_id == store_id)
    if change_type:
        query = query.filter(StockLedger.change_type == change_type)
    rows = query.order_by(StockLedger.ts.desc(), StockLedger.id.desc()).limit(limit).all()
    return [{
        "id": r.id, "ts": r.ts.strftime("%Y-%m-%d %H:%M:%S"),
        "store_name": store.name if store else "—",
        "drug_name": drug.name, "batch_no": batch.batch_no,
        "change_type": r.change_type, "qty_change": r.qty_change,
        "balance_after": r.balance_after, "ref_no": r.ref_no,
        "operator": r.operator, "note": r.note,
    } for r, batch, drug, store in rows]


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db)):
    apply_expiry_locks(db, date.today())
    db.commit()
    today = date.today()

    batches = db.query(Batch).all()
    on_hand = dict(db.query(Inventory.batch_id, func.sum(Inventory.quantity))
                   .group_by(Inventory.batch_id).all())

    near_expiry, expired_locked, qc_suspended = [], 0, 0
    for b in batches:
        qty = int(on_hand.get(b.id, 0) or 0)
        if b.status == BatchStatus.EXPIRED_LOCKED:
            expired_locked += 1
        elif b.status == BatchStatus.QC_SUSPENDED:
            qc_suspended += 1
        elif qty > 0 and is_near_expiry(b, today):
            near_expiry.append(b.id)

    near_rows = []
    if near_expiry:
        for b, d in (db.query(Batch, Drug).join(Drug, Batch.drug_id == Drug.id)
                     .filter(Batch.id.in_(near_expiry)).order_by(Batch.expiry_date).all()):
            near_rows.append({
                "batch_id": b.id, "drug_name": d.name, "spec": d.spec, "unit": d.unit,
                "batch_no": b.batch_no, "expiry_date": b.expiry_date.isoformat(),
                "days_to_expiry": (b.expiry_date - today).days,
                "on_hand": int(on_hand.get(b.id, 0) or 0),
            })

    in_transit = (db.query(Transfer)
                  .filter(Transfer.status == TransferStatus.IN_TRANSIT)
                  .order_by(Transfer.created_at.desc()).all())
    store_names = {s.id: s.name for s in db.query(Store).all()}
    batch_map = {b.id: b for b in batches}
    drug_map = {d.id: d for d in db.query(Drug).all()}

    return {
        "drug_count": db.query(Drug).count(),
        "batch_count": len(batches),
        "store_count": db.query(Store).filter(Store.is_warehouse.is_(False)).count(),
        "total_units": int(sum(on_hand.values()) or 0),
        "near_expiry_count": len(near_rows),
        "expired_locked_count": expired_locked,
        "qc_suspended_count": qc_suspended,
        "in_transit_count": len(in_transit),
        "near_expiry": near_rows,
        "in_transit_list": [{
            "transfer_no": t.transfer_no,
            "drug_name": drug_map[batch_map[t.batch_id].drug_id].name,
            "batch_no": batch_map[t.batch_id].batch_no,
            "from_store": store_names.get(t.from_store_id, "?"),
            "to_store": store_names.get(t.to_store_id, "?"),
            "quantity": t.quantity,
            "shipped_at": t.created_at.strftime("%Y-%m-%d %H:%M"),
        } for t in in_transit],
    }


@router.get("/qc-records")
def qc_records(db: Session = Depends(get_db)):
    rows = (db.query(QCRecord, Batch, Drug)
            .join(Batch, QCRecord.batch_id == Batch.id)
            .join(Drug, Batch.drug_id == Drug.id)
            .order_by(QCRecord.created_at.desc()).limit(200).all())
    return [{
        "id": r.id, "drug_name": d.name, "batch_no": b.batch_no,
        "action": r.action, "reason": r.reason, "release_doc_no": r.release_doc_no,
        "operator": r.operator, "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S"),
    } for r, b, d in rows]
