"""月度报表模块。

每月 1 号要看的两张账（可指定任意年月，默认上月）：
1. 近效期清单：以月末为快照日，效期落在快照日后 6 个月内、且月末仍有库存的批次；
   另列月末已过期未清、质检停售的批次。
2. 批次流向表：按批次汇总 月初存量 / 本月入库 / 本月销售(含拆零) /
   本月调拨发出 / 本月调拨收入 / 月末存量，全局满足
   月末存量 = 月初存量 + 本月入库 - 本月销售（在途量单列）。

所有数字直接从带时间戳的批次级流水重算，不依赖当前库存，历史月份也能复账。
"""
from datetime import date, datetime, timedelta

from sqlalchemy import func, select

from ..models import (
    Batch,
    BATCH_HOLD,
    Drug,
    Inbound,
    Location,
    Outbound,
    OutboundFlow,
    Stock,
    Transfer,
    TRANSIT,
    TransferItem,
)
from .expiry import _SIX_MONTH_DAYS


def _month_bounds(year: int, month: int) -> tuple[datetime, datetime, date]:
    start = datetime(year, month, 1)
    if month == 12:
        end = datetime(year + 1, 1, 1)
        end_date = date(year + 1, 1, 1)
    else:
        end = datetime(year, month + 1, 1)
        end_date = date(year, month + 1, 1)
    return start, end, end_date


def _sum_dict(rows) -> dict:
    return {batch_id: int(qty) for batch_id, qty in rows}


def monthly_report(db, year: int, month: int) -> dict:
    start_dt, end_dt, end_date = _month_bounds(year, month)

    batches = db.scalars(select(Batch)).all()
    batch_map = {b.id: b for b in batches}
    drugs = {d.id: d for d in db.scalars(select(Drug)).all()}

    # ---------- 入库（只进总仓）：月前 / 当月 ----------
    inb_before = _sum_dict(db.execute(
        select(Inbound.batch_id, func.coalesce(func.sum(Inbound.qty), 0))
        .where(Inbound.created_at < start_dt).group_by(Inbound.batch_id)
    ).all())
    inb_month = _sum_dict(db.execute(
        select(Inbound.batch_id, func.coalesce(func.sum(Inbound.qty), 0))
        .where(Inbound.created_at >= start_dt, Inbound.created_at < end_dt)
        .group_by(Inbound.batch_id)
    ).all())

    # ---------- 销售出库（含拆零）：月前 / 当月 ----------
    out_before = _sum_dict(db.execute(
        select(OutboundFlow.batch_id, func.coalesce(func.sum(OutboundFlow.qty), 0))
        .join(Outbound, Outbound.id == OutboundFlow.outbound_id)
        .where(Outbound.created_at < start_dt).group_by(OutboundFlow.batch_id)
    ).all())
    out_month = _sum_dict(db.execute(
        select(OutboundFlow.batch_id, func.coalesce(func.sum(OutboundFlow.qty), 0))
        .join(Outbound, Outbound.id == OutboundFlow.outbound_id)
        .where(Outbound.created_at >= start_dt, Outbound.created_at < end_dt)
        .group_by(OutboundFlow.batch_id)
    ).all())

    # ---------- 调拨发出 ----------
    ship_before = _sum_dict(db.execute(
        select(TransferItem.batch_id, func.coalesce(func.sum(TransferItem.qty), 0))
        .join(Transfer, Transfer.id == TransferItem.transfer_id)
        .where(Transfer.shipped_at < start_dt).group_by(TransferItem.batch_id)
    ).all())
    ship_month = _sum_dict(db.execute(
        select(TransferItem.batch_id, func.coalesce(func.sum(TransferItem.qty), 0))
        .join(Transfer, Transfer.id == TransferItem.transfer_id)
        .where(Transfer.shipped_at >= start_dt, Transfer.shipped_at < end_dt)
        .group_by(TransferItem.batch_id)
    ).all())

    # ---------- 调拨收入（按实际收货时间）----------
    recv_before = _sum_dict(db.execute(
        select(TransferItem.batch_id, func.coalesce(func.sum(TransferItem.qty), 0))
        .join(Transfer, Transfer.id == TransferItem.transfer_id)
        .where(Transfer.received_at.is_not(None), Transfer.received_at < start_dt)
        .group_by(TransferItem.batch_id)
    ).all())
    recv_month = _sum_dict(db.execute(
        select(TransferItem.batch_id, func.coalesce(func.sum(TransferItem.qty), 0))
        .join(Transfer, Transfer.id == TransferItem.transfer_id)
        .where(Transfer.received_at.is_not(None),
               Transfer.received_at >= start_dt, Transfer.received_at < end_dt)
        .group_by(TransferItem.batch_id)
    ).all())

    # ---------- 批次流向行 ----------
    flow_rows = []
    near_rows, expired_rows, hold_rows = [], [], []

    for bid, b in sorted(batch_map.items(), key=lambda kv: (kv[1].expiry_date, kv[0])):
        opening = inb_before.get(bid, 0) - out_before.get(bid, 0)
        inb = inb_month.get(bid, 0)
        sold = out_month.get(bid, 0)
        shipped = ship_month.get(bid, 0)
        received = recv_month.get(bid, 0)
        closing = opening + inb - sold
        # 月末在途：月末前已发、月末前未收
        transit_end = ship_before.get(bid, 0) + shipped - recv_before.get(bid, 0) - received
        if transit_end < 0:
            transit_end = 0  # 极端时钟错乱下不为负
        on_shelf_end = closing - transit_end  # 月末在架库存

        d = drugs[b.drug_id]
        row = {
            "batch_id": bid,
            "drug_code": d.code,
            "drug_name": d.name,
            "spec": d.spec,
            "batch_no": b.batch_no,
            "production_date": b.production_date.isoformat(),
            "expiry_date": b.expiry_date.isoformat(),
            "supplier": b.supplier,
            "opening_qty": opening,
            "inbound_qty": inb,
            "sold_qty": sold,
            "shipped_qty": shipped,
            "received_qty": received,
            "in_transit_qty": transit_end,
            "on_shelf_qty": on_shelf_end,
            "closing_qty": closing,
            "quality_status": b.status,
        }
        if opening or inb or sold or shipped or received or closing:
            flow_rows.append(row)

        # 月末快照三清单（只列月末仍有货的批）
        if closing > 0:
            if b.expiry_date < end_date:
                expired_rows.append(row)
            elif b.expiry_date <= end_date + timedelta(days=_SIX_MONTH_DAYS):
                near_rows.append(row)
            if b.status == BATCH_HOLD:
                hold_rows.append(row)

    # ---------- 当前实时库存（与月报月末数分开，方便对照）----------
    live_stock = _live_stock(db)

    return {
        "period": {"year": year, "month": month,
                   "start": start_dt.date().isoformat(),
                   "end": end_date.isoformat()},
        "near_expiry": near_rows,
        "expired": expired_rows,
        "quality_hold": hold_rows,
        "batch_flows": flow_rows,
        "live_stock": live_stock,
    }


def _live_stock(db) -> list[dict]:
    """报表附当前实时库存（批次×货位），用于月末账与今天实物对照。"""
    locations = {l.id: l for l in db.scalars(select(Location)).all()}
    batches = {b.id: b for b in db.scalars(select(Batch)).all()}
    drugs = {d.id: d for d in db.scalars(select(Drug)).all()}

    rows = []
    for stock, batch in db.execute(
        select(Stock, Batch).join(Batch, Batch.id == Stock.batch_id)
        .where(Stock.qty > 0).order_by(Batch.expiry_date)
    ).all():
        loc = locations[stock.location_id]
        d = drugs[batch.drug_id]
        rows.append({
            "drug_name": d.name, "spec": d.spec, "batch_no": batch.batch_no,
            "expiry_date": batch.expiry_date.isoformat(),
            "location": loc.name, "qty": stock.qty, "unit": d.unit,
            "quality_status": batch.status,
        })
    return rows
