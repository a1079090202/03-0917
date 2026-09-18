"""模块一：出库扣减。

死规矩实现：
- 同一个药先出效期最近的批（FEFO），一批不够才动下一批；
- 支持手工指定批次，但指定结果必须与 FEFO 应出结果一致，
  否则拒单并指出应当先出的批号 —— 先出效期远的批，系统不认；
- 过期批、质检停售批一律禁止出库；
- 扣减走"事务 + 条件更新"：UPDATE inventory SET quantity = quantity - n
  WHERE id = ? AND quantity >= n，影响行数不为 1 即整单回滚，
  两人同时出最后一批不会卖穿，账上不会出现负数；
- 每动一批写一条库存流水；拆零销售另写拆零台账。
"""
from datetime import datetime
from typing import Iterable, NamedTuple

from sqlalchemy import update
from sqlalchemy.orm import Session

from ..models import (Batch, BatchStatus, Inventory, LedgerType, OrderType,
                      OutboundItem, OutboundOrder, SplitRecord, StockLedger)
from .common import BizError, gen_no
from .expiry_lock import apply_expiry_locks


class Allocation(NamedTuple):
    inventory: Inventory
    batch: Batch
    quantity: int


def _sellable_batches(db: Session, store_id: int, drug_id: int, on_date) -> list[tuple[Inventory, Batch]]:
    """该店该药当前可售批次，按效期升序（效期最近的在前）。"""
    return (
        db.query(Inventory, Batch)
        .join(Batch, Inventory.batch_id == Batch.id)
        .filter(
            Inventory.store_id == store_id,
            Batch.drug_id == drug_id,
            Inventory.quantity > 0,
            Batch.status == BatchStatus.NORMAL,
            Batch.expiry_date >= on_date,
        )
        .order_by(Batch.expiry_date.asc(), Batch.id.asc())
        .all()
    )


def allocate_fefo(db: Session, store_id: int, drug_id: int, quantity: int, on_date) -> list[Allocation]:
    """按效期最近优先自动分配；总可售不足则拒单。"""
    allocations: list[Allocation] = []
    remaining = quantity
    for inv, batch in _sellable_batches(db, store_id, drug_id, on_date):
        take = min(inv.quantity, remaining)
        allocations.append(Allocation(inv, batch, take))
        remaining -= take
        if remaining == 0:
            break
    if remaining > 0:
        raise BizError(f"可售库存不足：还差 {remaining}（已按效期优先汇总所有可售批次）", 409)
    return allocations


def _validate_manual(db: Session, store_id: int, drug_id: int, quantity: int,
                     manual: Iterable, on_date) -> list[Allocation]:
    """校验手工指定的批次分配：先过效期/停售红线，再与 FEFO 应出结果逐批比对。"""
    requested: dict[int, int] = {}
    for a in manual:
        requested[a.batch_id] = requested.get(a.batch_id, 0) + a.quantity
    if sum(requested.values()) != quantity:
        raise BizError("手工指定批次的数量合计必须等于出库数量")

    for batch_id in requested:
        batch = db.get(Batch, batch_id)
        if batch is None or batch.drug_id != drug_id:
            raise BizError("指定的批次不存在或不属于该药品")
        if batch.status == BatchStatus.EXPIRED_LOCKED or batch.expiry_date < on_date:
            raise BizError(f"批次 {batch.batch_no} 已过有效期（{batch.expiry_date.isoformat()}），已锁死，禁止出库")
        if batch.status == BatchStatus.QC_SUSPENDED:
            raise BizError(f"批次 {batch.batch_no} 质检停售中，禁止出库")

    ideal = allocate_fefo(db, store_id, drug_id, quantity, on_date)
    ideal_map = {a.batch.id: a.quantity for a in ideal}
    if requested != ideal_map:
        for a in ideal:  # ideal 按效期升序，找到第一个被违反的批次
            if requested.get(a.batch.id) != a.quantity:
                raise BizError(
                    f"违反效期先出原则：批次 {a.batch.batch_no}（有效期至 "
                    f"{a.batch.expiry_date.isoformat()}）尚未出完，不允许先出效期更远的批"
                )
        raise BizError("手工分配与效期先出原则不一致")
    return ideal


def deduct_inventory(db: Session, inv: Inventory, quantity: int) -> None:
    """条件更新扣减：库存不够或已被并发扣掉时影响行数为 0，立即失败。

    调拨模块同样走这里 —— 全系统只有这一个库存扣减出口。
    """
    res = db.execute(
        update(Inventory)
        .where(Inventory.id == inv.id, Inventory.quantity >= quantity)
        .values(quantity=Inventory.quantity - quantity)
    )
    if res.rowcount != 1:
        db.rollback()
        raise BizError("库存不足（可能刚被其他出库占用），请刷新后重试", 409)


def create_outbound(db: Session, *, store_id: int, order_type: str, operator: str,
                    items: Iterable, when: datetime | None = None,
                    commit: bool = True) -> OutboundOrder:
    if order_type not in (OrderType.SALE, OrderType.SPLIT_SALE):
        raise BizError("出库类型只能是 SALE（销售）或 SPLIT_SALE（拆零）")
    when = when or datetime.now()
    on_date = when.date()
    apply_expiry_locks(db, on_date)  # 动账前先锁过期批

    order = OutboundOrder(
        order_no=gen_no("OUT", when), store_id=store_id,
        order_type=order_type, operator=operator, created_at=when,
    )
    db.add(order)
    db.flush()

    ledger_type = LedgerType.SPLIT_SALE if order_type == OrderType.SPLIT_SALE else LedgerType.SALE
    for item in items:
        if item.quantity <= 0:
            raise BizError("出库数量必须为正整数")
        if item.allocations:
            allocations = _validate_manual(db, store_id, item.drug_id, item.quantity,
                                           item.allocations, on_date)
        else:
            allocations = allocate_fefo(db, store_id, item.drug_id, item.quantity, on_date)
        for alloc in allocations:
            deduct_inventory(db, alloc.inventory, alloc.quantity)
            db.add(OutboundItem(order_id=order.id, batch_id=alloc.batch.id, quantity=alloc.quantity))
            db.add(StockLedger(
                ts=when, store_id=store_id, batch_id=alloc.batch.id,
                change_type=ledger_type, qty_change=-alloc.quantity,
                balance_after=alloc.inventory.quantity - alloc.quantity,
                ref_type="OUTBOUND", ref_id=order.id, ref_no=order.order_no,
                operator=operator,
                note=f"批号 {alloc.batch.batch_no}，有效期至 {alloc.batch.expiry_date.isoformat()}",
            ))
            if order_type == OrderType.SPLIT_SALE:
                db.add(SplitRecord(
                    ts=when, store_id=store_id, drug_id=item.drug_id,
                    batch_id=alloc.batch.id, quantity=alloc.quantity,
                    operator=operator, outbound_order_id=order.id,
                ))
    db.flush()
    if commit:
        db.commit()
        db.refresh(order)
    return order


def preview_outbound(db: Session, *, store_id: int, drug_id: int, quantity: int) -> list[dict]:
    """出库预览：只算 FEFO 分配，不动账。"""
    today = datetime.now().date()
    apply_expiry_locks(db, today)
    db.commit()  # 锁定结果落库，预览本身不改库存
    return [
        {
            "batch_id": a.batch.id,
            "batch_no": a.batch.batch_no,
            "expiry_date": a.batch.expiry_date.isoformat(),
            "available": a.inventory.quantity,
            "take": a.quantity,
        }
        for a in allocate_fefo(db, store_id, drug_id, quantity, today)
    ]
