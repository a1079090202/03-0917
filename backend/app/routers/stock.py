"""档案与库存台账查询：药品、门店、批次台账、批次×货位库存、各类流水。"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (
    Batch,
    Drug,
    Inbound,
    Location,
    Outbound,
    OutboundFlow,
    QualityAction,
    SplitSale,
    Stock,
    Transfer,
    TransferItem,
)
from ..services.expiry import batch_flag, is_near_expiry, is_expired

router = APIRouter(prefix="/api", tags=["档案与台账"])


@router.get("/drugs")
def list_drugs(db: Session = Depends(get_db)):
    drugs = db.scalars(select(Drug).order_by(Drug.code)).all()
    return [{"id": d.id, "code": d.code, "name": d.name, "spec": d.spec,
             "manufacturer": d.manufacturer, "unit": d.unit,
             "bulk_unit": d.bulk_unit, "bulk_size": d.bulk_size} for d in drugs]


@router.get("/locations")
def list_locations(db: Session = Depends(get_db)):
    locs = db.scalars(select(Location).order_by(Location.kind.desc(), Location.code)).all()
    return [{"id": l.id, "code": l.code, "name": l.name, "kind": l.kind} for l in locs]


def _stock_distribution(db, batch_id: int) -> list[dict]:
    rows = db.execute(
        select(Location.id, Location.code, Location.name, Location.kind, Stock.qty)
        .join(Stock, Stock.location_id == Location.id)
        .where(Stock.batch_id == batch_id, Stock.qty > 0)
        .order_by(Location.kind.desc(), Location.code)
    ).all()
    return [{"location_id": r[0], "location_code": r[1], "location_name": r[2],
             "kind": r[3], "qty": r[4]} for r in rows]


@router.get("/batches")
def list_batches(
    drug_id: int | None = None,
    location_id: int | None = None,
    flag: str | None = Query(None, description="normal/near/expired/hold"),
    only_stock: bool = True,
    db: Session = Depends(get_db),
):
    """批次台账：每批的药品信息、效期标记、总库存与各货位分布。"""
    today = date.today()
    stmt = (
        select(Batch, Drug, func.coalesce(func.sum(Stock.qty), 0))
        .join(Drug, Drug.id == Batch.drug_id)
        .outerjoin(Stock, Stock.batch_id == Batch.id)
    )
    if drug_id:
        stmt = stmt.where(Batch.drug_id == drug_id)
    if location_id:
        stmt = stmt.where(
            Stock.location_id == location_id
        )
    stmt = stmt.group_by(Batch.id).order_by(Batch.expiry_date.asc(), Drug.name)

    result = []
    for b, d, total_qty in db.execute(stmt).all():
        if only_stock and (location_id is None) and total_qty == 0:
            continue
        f = batch_flag(b, today)
        if flag and f != flag:
            continue
        result.append({
            "id": b.id,
            "drug_id": d.id,
            "drug_code": d.code,
            "drug_name": d.name,
            "spec": d.spec,
            "manufacturer": d.manufacturer,
            "unit": d.unit,
            "bulk_unit": d.bulk_unit,
            "bulk_size": d.bulk_size,
            "batch_no": b.batch_no,
            "production_date": b.production_date.isoformat(),
            "expiry_date": b.expiry_date.isoformat(),
            "supplier": b.supplier,
            "quality_status": b.status,
            "flag": f,
            "near_expiry": is_near_expiry(b, today),
            "expired": is_expired(b, today),
            "total_qty": int(total_qty),
            "distribution": _stock_distribution(db, b.id),
        })
    return result


@router.get("/batches/{batch_id}")
def get_batch(batch_id: int, db: Session = Depends(get_db)):
    b = db.get(Batch, batch_id)
    if b is None:
        raise HTTPException(status_code=404, detail="批次不存在")
    d = db.get(Drug, b.drug_id)
    return {
        "id": b.id, "drug_id": d.id, "drug_code": d.code, "drug_name": d.name,
        "spec": d.spec, "batch_no": b.batch_no,
        "production_date": b.production_date.isoformat(),
        "expiry_date": b.expiry_date.isoformat(),
        "supplier": b.supplier, "quality_status": b.status,
        "flag": batch_flag(b),
        "distribution": _stock_distribution(db, b.id),
    }


# ---------------------------------------------------------------- 流水查询

@router.get("/ledger/inbound")
def ledger_inbound(limit: int = 200, db: Session = Depends(get_db)):
    rows = db.execute(
        select(Inbound, Drug.name, Drug.unit)
        .join(Drug, Drug.id == Inbound.drug_id)
        .order_by(Inbound.created_at.desc(), Inbound.id.desc()).limit(limit)
    ).all()
    return [{
        "no": r.no, "time": r.created_at.isoformat(timespec="seconds"),
        "drug_name": name, "batch_id": r.batch_id,
        "batch_no": db.get(Batch, r.batch_id).batch_no,
        "production_date": r.production_date.isoformat(),
        "expiry_date": r.expiry_date.isoformat(),
        "qty": r.qty, "unit": unit, "supplier": r.supplier,
        "operator": r.operator, "note": r.note,
    } for r, name, unit in rows]


@router.get("/ledger/outbound")
def ledger_outbound(limit: int = 200, db: Session = Depends(get_db)):
    heads = db.scalars(
        select(Outbound).order_by(Outbound.created_at.desc(), Outbound.id.desc()).limit(limit)
    ).all()
    loc_map = {l.id: l.name for l in db.scalars(select(Location)).all()}
    drug_map = {d.id: (d.name, d.unit) for d in db.scalars(select(Drug)).all()}
    out = []
    for h in heads:
        flows = db.scalars(
            select(OutboundFlow).where(OutboundFlow.outbound_id == h.id)
            .order_by(OutboundFlow.expiry_date)
        ).all()
        name, unit = drug_map[h.drug_id]
        out.append({
            "no": h.no, "time": h.created_at.isoformat(timespec="seconds"),
            "drug_name": name, "unit": unit, "kind": h.kind,
            "location": loc_map.get(h.location_id), "qty": h.qty,
            "operator": h.operator, "note": h.note,
            "flows": [{
                "batch_id": f.batch_id,
                "batch_no": db.get(Batch, f.batch_id).batch_no,
                "expiry_date": f.expiry_date.isoformat(), "qty": f.qty,
            } for f in flows],
        })
    return out


@router.get("/ledger/splits")
def ledger_splits(limit: int = 200, db: Session = Depends(get_db)):
    """拆零台账单独一本。"""
    rows = db.execute(
        select(SplitSale, Drug.name, Drug.unit, Drug.bulk_unit, Drug.bulk_size,
               Batch.batch_no, Location.name)
        .join(Batch, Batch.id == SplitSale.batch_id)
        .join(Drug, Drug.id == Batch.drug_id)
        .join(Location, Location.id == SplitSale.location_id)
        .order_by(SplitSale.id.desc()).limit(limit)
    ).all()
    return [{
        "time": s.created_at.isoformat(timespec="seconds"),
        "outbound_no": db.get(Outbound, s.outbound_id).no,
        "drug_name": name, "batch_no": batch_no, "location": loc_name,
        "qty": s.qty, "unit": unit,
        "bulk_packages": s.bulk_packages, "bulk_unit": bulk_unit,
        "loose_units": s.loose_units,
    } for s, name, unit, bulk_unit, bulk_size, batch_no, loc_name in rows]


@router.get("/ledger/transfers")
def ledger_transfers(limit: int = 200, db: Session = Depends(get_db)):
    loc_map = {l.id: l.name for l in db.scalars(select(Location)).all()}
    drug_map = {d.id: (d.name, d.unit) for d in db.scalars(select(Drug)).all()}
    ts = db.scalars(
        select(Transfer).order_by(Transfer.shipped_at.desc(), Transfer.id.desc()).limit(limit)
    ).all()
    out = []
    for t in ts:
        items = db.scalars(select(TransferItem).where(TransferItem.transfer_id == t.id)).all()
        name, unit = drug_map[t.drug_id]
        out.append({
            "id": t.id, "no": t.no, "drug_name": name, "unit": unit,
            "from": loc_map[t.from_location_id], "to": loc_map[t.to_location_id],
            "qty": t.qty, "status": t.status,
            "shipped_at": t.shipped_at.isoformat(timespec="seconds"),
            "received_at": t.received_at.isoformat(timespec="seconds") if t.received_at else None,
            "operator": t.operator,
            "items": [{
                "batch_no": db.get(Batch, i.batch_id).batch_no,
                "expiry_date": i.expiry_date.isoformat(), "qty": i.qty,
            } for i in items],
        })
    return out


@router.get("/ledger/quality")
def ledger_quality(limit: int = 200, db: Session = Depends(get_db)):
    rows = db.execute(
        select(QualityAction, Drug.name, Batch.batch_no)
        .join(Batch, Batch.id == QualityAction.batch_id)
        .join(Drug, Drug.id == Batch.drug_id)
        .order_by(QualityAction.created_at.desc(), QualityAction.id.desc()).limit(limit)
    ).all()
    return [{
        "no": q.no, "time": q.created_at.isoformat(timespec="seconds"),
        "drug_name": name, "batch_no": batch_no, "action": q.action,
        "doc_no": q.doc_no, "reason": q.reason, "operator": q.operator,
    } for q, name, batch_no in rows]
