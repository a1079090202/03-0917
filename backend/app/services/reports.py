"""模块四：报表。

每月 1 号看上月：
- 近效期清单：截至月末效期落入 6 个月预警窗、且月末仍有库存的批次；
- 批次流向表：每批次 期初 / 入库 / 销售 / 拆零 / 调入 / 调出 / 期末，
  全部从库存流水汇总，期初 + 变动 = 期末，与台账逐笔可对。
"""
import calendar
from collections import defaultdict
from datetime import date, datetime

from sqlalchemy.orm import Session

from ..models import (Batch, Drug, LedgerType, StockLedger, Store)
from .common import BizError
from .expiry_lock import NEAR_EXPIRY_MONTHS, add_months, apply_expiry_locks


def _month_range(month: str) -> tuple[datetime, datetime]:
    try:
        y, m = int(month[:4]), int(month[5:7])
        assert 1 <= m <= 12
    except (ValueError, IndexError, AssertionError):
        raise BizError("月份格式应为 YYYY-MM，如 2026-08")
    start = datetime(y, m, 1)
    last_day = calendar.monthrange(y, m)[1]
    end = datetime(y, m, last_day, 23, 59, 59)
    return start, end


def _ledger_rows(db: Session) -> list[StockLedger]:
    return db.query(StockLedger).all()


def monthly_flow(db: Session, month: str) -> dict:
    """批次流向表（全连锁口径，按批次汇总）+ 门店汇总。"""
    start, end = _month_range(month)
    rows = _ledger_rows(db)

    batches = {b.id: b for b in db.query(Batch).all()}
    drugs = {d.id: d for d in db.query(Drug).all()}
    stores = {s.id: s for s in db.query(Store).all()}

    per_batch = defaultdict(lambda: {"opening": 0, "inbound": 0, "sale": 0, "split_sale": 0,
                                     "transfer_in": 0, "transfer_out": 0, "closing": 0})
    per_store = defaultdict(lambda: {"inbound": 0, "sale": 0, "split_sale": 0,
                                     "transfer_in": 0, "transfer_out": 0})
    for r in rows:
        if r.change_type in (LedgerType.EXPIRY_LOCK, LedgerType.QC_SUSPEND, LedgerType.QC_RELEASE):
            continue  # 状态类流水不动数量
        b = per_batch[r.batch_id]
        if r.ts < start:
            b["opening"] += r.qty_change
            continue
        if r.ts > end:
            continue
        key = {
            LedgerType.INBOUND: "inbound",
            LedgerType.SALE: "sale",
            LedgerType.SPLIT_SALE: "split_sale",
            LedgerType.TRANSFER_IN: "transfer_in",
            LedgerType.TRANSFER_OUT: "transfer_out",
        }[r.change_type]
        b[key] += -r.qty_change if key in ("sale", "split_sale", "transfer_out") else r.qty_change
        if r.store_id in stores:
            per_store[r.store_id][key] += abs(r.qty_change)

    batch_rows = []
    totals = defaultdict(int)
    for batch_id, agg in sorted(per_batch.items(), key=lambda kv: kv[0]):
        closing = agg["opening"] + agg["inbound"] + agg["transfer_in"] \
                  - agg["sale"] - agg["split_sale"] - agg["transfer_out"]
        if closing == 0 and not any(agg[k] for k in ("opening", "inbound", "sale", "split_sale",
                                                     "transfer_in", "transfer_out")):
            continue
        batch = batches.get(batch_id)
        drug = drugs.get(batch.drug_id) if batch else None
        batch_rows.append({
            "batch_id": batch_id,
            "drug_name": drug.name if drug else "?",
            "spec": drug.spec if drug else "",
            "unit": drug.unit if drug else "",
            "batch_no": batch.batch_no if batch else "?",
            "expiry_date": batch.expiry_date.isoformat() if batch else "",
            "opening": agg["opening"],
            "inbound": agg["inbound"],
            "sale": agg["sale"],
            "split_sale": agg["split_sale"],
            "transfer_in": agg["transfer_in"],
            "transfer_out": agg["transfer_out"],
            "closing": closing,
        })
        for k in ("opening", "inbound", "sale", "split_sale", "transfer_in", "transfer_out", "closing"):
            totals[k] += batch_rows[-1][k]

    store_rows = [{
        "store_id": sid,
        "store_name": stores[sid].name,
        **agg,
    } for sid, agg in sorted(per_store.items())]

    return {
        "month": month,
        "batches": batch_rows,
        "totals": dict(totals),
        "stores": store_rows,
    }


def near_expiry_report(db: Session, month: str) -> dict:
    """近效期清单：截至该月末，效期 <= 月末+6个月 且月末结存 > 0 的批次。"""
    apply_expiry_locks(db, date.today())
    start, end = _month_range(month)
    threshold = add_months(end.date(), NEAR_EXPIRY_MONTHS)
    today = date.today()

    # 月末结存 = 月末之前所有数量流水的代数和（按批次）
    closing = defaultdict(int)
    for r in _ledger_rows(db):
        if r.ts <= end and r.change_type in (
            LedgerType.INBOUND, LedgerType.SALE, LedgerType.SPLIT_SALE,
            LedgerType.TRANSFER_IN, LedgerType.TRANSFER_OUT,
        ):
            closing[r.batch_id] += r.qty_change

    drugs = {d.id: d for d in db.query(Drug).all()}
    items = []
    for batch in db.query(Batch).filter(Batch.expiry_date <= threshold).order_by(Batch.expiry_date).all():
        qty = closing.get(batch.id, 0)
        if qty <= 0:
            continue
        drug = drugs[batch.drug_id]
        expired = batch.expiry_date < today
        items.append({
            "batch_id": batch.id,
            "drug_name": drug.name,
            "spec": drug.spec,
            "unit": drug.unit,
            "batch_no": batch.batch_no,
            "expiry_date": batch.expiry_date.isoformat(),
            "days_to_expiry": (batch.expiry_date - today).days,
            "quantity_at_month_end": qty,
            "status": batch.status,
            "expired": expired,
        })
    return {
        "month": month,
        "window_months": NEAR_EXPIRY_MONTHS,
        "threshold": threshold.isoformat(),
        "items": items,
    }
