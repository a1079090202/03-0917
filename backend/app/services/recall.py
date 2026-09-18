"""召回追溯模块。

输一个批号，一口气列出：
- 每家门店/总仓 收到多少（入库进总仓、调拨进门店）、
  卖出多少（含拆零）、调出多少、当前还剩多少；
- 还压在调拨途中的货：哪张单调拨单、从哪到哪、多少；
- 该批全部流水（入库/出库/调拨发收/质检）按时间排好。

口径：所有数字按批次直接从批次级流水汇总，不依赖"当前库存推算历史"，
纸面流向和系统能一一对上。
"""
from datetime import datetime

from sqlalchemy import func, select

from ..models import (
    Batch,
    Drug,
    Inbound,
    Location,
    Outbound,
    OutboundFlow,
    QualityAction,
    RecallNotice,
    Stock,
    Transfer,
    TRANSIT,
    TransferItem,
)
from .inventory import BizError


def register_recall(db, *, batch_id, no, issuer, issued_date, note=None) -> dict:
    batch = db.get(Batch, batch_id)
    if batch is None:
        raise BizError(f"批次不存在：id={batch_id}")
    if db.scalar(select(RecallNotice).where(RecallNotice.no == no)):
        raise BizError(f"召回函号 {no} 已登记，不能重复")
    db.add(RecallNotice(
        no=no, batch_id=batch_id, issuer=issuer, issued_date=issued_date,
        note=note, created_at=datetime.now(),
    ))
    db.commit()
    return {"no": no}


def trace_by_batch(db, *, batch_no: str, drug_id: int | None = None) -> dict:
    cond = [Batch.batch_no == batch_no]
    if drug_id is not None:
        cond.append(Batch.drug_id == drug_id)
    batch = db.scalar(select(Batch).where(*cond))
    if batch is None:
        raise BizError(f"台账中查不到批号 {batch_no}")

    drug = db.get(Drug, batch.drug_id)
    locations = db.scalars(select(Location).order_by(Location.kind, Location.code)).all()
    loc_map = {l.id: l for l in locations}

    # ---- 当前库存（各货位）----
    stock_map = dict(db.execute(
        select(Stock.location_id, Stock.qty)
        .where(Stock.batch_id == batch.id, Stock.qty > 0)
    ).all())

    # ---- 总仓进货 = 入库累计 ----
    inbound_total = db.scalar(
        select(func.coalesce(func.sum(Inbound.qty), 0)).where(Inbound.batch_id == batch.id)
    )

    # ---- 门店收入 = 已收货调拨单中调入该门店的该批数量 ----
    received_qty = dict(db.execute(
        select(Transfer.to_location_id, func.coalesce(func.sum(TransferItem.qty), 0))
        .join(TransferItem, TransferItem.transfer_id == Transfer.id)
        .where(TransferItem.batch_id == batch.id, Transfer.status == "received")
        .group_by(Transfer.to_location_id)
    ).all())

    # ---- 销售（含拆零），出库流水按货位汇总 ----
    sold_qty = dict(db.execute(
        select(OutboundFlow.location_id, func.coalesce(func.sum(OutboundFlow.qty), 0))
        .where(OutboundFlow.batch_id == batch.id)
        .group_by(OutboundFlow.location_id)
    ).all())

    # ---- 调出量（已发出即算，含在途）----
    shipped_out_qty = dict(db.execute(
        select(Transfer.from_location_id, func.coalesce(func.sum(TransferItem.qty), 0))
        .join(TransferItem, TransferItem.transfer_id == Transfer.id)
        .where(TransferItem.batch_id == batch.id)
        .group_by(Transfer.from_location_id)
    ).all())

    # ---- 在途：未收货调拨单逐单列 ----
    transit_rows = db.execute(
        select(Transfer, TransferItem.qty)
        .join(TransferItem, TransferItem.transfer_id == Transfer.id)
        .where(TransferItem.batch_id == batch.id, Transfer.status == TRANSIT)
        .order_by(Transfer.shipped_at)
    ).all()

    locations_view = []
    for loc in locations:
        received = inbound_total if loc.kind == "warehouse" else received_qty.get(loc.id, 0)
        sold = sold_qty.get(loc.id, 0)
        shipped = shipped_out_qty.get(loc.id, 0)
        current = stock_map.get(loc.id, 0)
        # 全部门店都列出（含 0），避免召回核对时误以为漏店
        locations_view.append({
            "location_id": loc.id,
            "location_code": loc.code,
            "location_name": loc.name,
            "kind": loc.kind,
            "touched": bool(received or sold or shipped or current),
            "received_qty": int(received),
            "sold_qty": int(sold),
            "shipped_out_qty": int(shipped),
            "current_qty": int(current),
        })

    in_transit = [{
        "transfer_no": t.no,
        "from": loc_map[t.from_location_id].name,
        "to": loc_map[t.to_location_id].name,
        "qty": int(qty),
        "shipped_at": t.shipped_at.isoformat(timespec="seconds"),
    } for t, qty in transit_rows]

    # ---- 全量批次流水（纸面对账用）----
    timeline = []
    for r in db.scalars(select(Inbound).where(Inbound.batch_id == batch.id)):
        timeline.append({
            "time": r.created_at.isoformat(timespec="seconds"),
            "type": "入库", "doc_no": r.no,
            "location": "总仓", "qty": r.qty, "party": r.supplier,
        })

    out_rows = db.execute(
        select(OutboundFlow, Outbound, Location.name)
        .join(Outbound, Outbound.id == OutboundFlow.outbound_id)
        .join(Location, Location.id == OutboundFlow.location_id)
        .where(OutboundFlow.batch_id == batch.id)
        .order_by(OutboundFlow.created_at)
    ).all()
    for flow, head, loc_name in out_rows:
        timeline.append({
            "time": flow.created_at.isoformat(timespec="seconds"),
            "type": "拆零销售" if head.kind == "split" else "销售出库",
            "doc_no": head.no, "location": loc_name,
            "qty": -flow.qty, "party": head.operator,
        })

    tr_rows = db.execute(
        select(Transfer, TransferItem.qty)
        .join(TransferItem, TransferItem.transfer_id == Transfer.id)
        .where(TransferItem.batch_id == batch.id).order_by(Transfer.shipped_at)
    ).all()
    for t, qty in tr_rows:
        timeline.append({
            "time": t.shipped_at.isoformat(timespec="seconds"),
            "type": "调拨发出" + ("（在途）" if t.status == TRANSIT else "（已收货）"),
            "doc_no": t.no,
            "location": f"{loc_map[t.from_location_id].name} → {loc_map[t.to_location_id].name}",
            "qty": -int(qty), "party": t.operator,
        })

    for q in db.scalars(select(QualityAction).where(QualityAction.batch_id == batch.id)):
        timeline.append({
            "time": q.created_at.isoformat(timespec="seconds"),
            "type": "质检停售" if q.action == "hold" else "质检放行",
            "doc_no": q.no, "location": "-", "qty": 0,
            "party": q.doc_no or q.reason or "",
        })
    timeline.sort(key=lambda x: x["time"])

    total_sold = sum(x["sold_qty"] for x in locations_view)
    total_current = sum(x["current_qty"] for x in locations_view)
    total_transit = sum(x["qty"] for x in in_transit)

    return {
        "batch": {
            "id": batch.id,
            "batch_no": batch.batch_no,
            "drug_code": drug.code,
            "drug_name": drug.name,
            "spec": drug.spec,
            "manufacturer": drug.manufacturer,
            "production_date": batch.production_date.isoformat(),
            "expiry_date": batch.expiry_date.isoformat(),
            "supplier": batch.supplier,
            "status": batch.status,
        },
        "summary": {
            # 全局恒等式：总入库（只进总仓）= 总销售 + 各货位现存 + 在途
            "total_received": int(inbound_total),
            "total_sold": total_sold,
            "total_current": total_current,
            "total_in_transit": total_transit,
            # 必须为 0，不为 0 就是账对不平
            "balance_check": int(inbound_total) - total_sold - total_current - total_transit,
        },
        "locations": locations_view,
        "in_transit": in_transit,
        "timeline": timeline,
    }
