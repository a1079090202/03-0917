"""调拨服务：门店/总仓之间移库，全程留痕。

- 创建调拨单即从发出方扣库存（与出库共用同一个条件更新扣减出口），状态为在途；
- 收货后入接收方库存，状态变已收货；
- 在途量单独可查 —— 召回追溯时"调拨途中压在哪"就看这里；
- 过期批、质检停售批禁止调拨。
"""
from datetime import datetime

from sqlalchemy.orm import Session

from ..models import (Batch, BatchStatus, Inventory, LedgerType, StockLedger,
                      Transfer, TransferStatus)
from .common import BizError, gen_no
from .expiry_lock import apply_expiry_locks
from .inbound import _get_or_create_inventory
from .outbound import deduct_inventory


def create_transfer(db: Session, *, from_store_id: int, to_store_id: int, batch_id: int,
                    quantity: int, operator: str, when: datetime | None = None,
                    commit: bool = True) -> Transfer:
    if from_store_id == to_store_id:
        raise BizError("调出与调入不能是同一门店")
    if quantity <= 0:
        raise BizError("调拨数量必须为正整数")
    when = when or datetime.now()
    on_date = when.date()
    apply_expiry_locks(db, on_date)

    batch = db.get(Batch, batch_id)
    if batch is None:
        raise BizError("批次不存在", 404)
    if batch.status == BatchStatus.EXPIRED_LOCKED or batch.expiry_date < on_date:
        raise BizError(f"批次 {batch.batch_no} 已过有效期，已锁死，禁止调拨")
    if batch.status == BatchStatus.QC_SUSPENDED:
        raise BizError(f"批次 {batch.batch_no} 质检停售中，禁止调拨")

    inv = (db.query(Inventory)
           .filter(Inventory.store_id == from_store_id, Inventory.batch_id == batch_id)
           .first())
    if inv is None or inv.quantity < quantity:
        raise BizError("调出方该批次库存不足", 409)

    t = Transfer(transfer_no=gen_no("TR", when), batch_id=batch_id,
                 from_store_id=from_store_id, to_store_id=to_store_id,
                 quantity=quantity, status=TransferStatus.IN_TRANSIT,
                 operator=operator, created_at=when)
    db.add(t)
    db.flush()

    deduct_inventory(db, inv, quantity)
    db.add(StockLedger(
        ts=when, store_id=from_store_id, batch_id=batch_id,
        change_type=LedgerType.TRANSFER_OUT, qty_change=-quantity,
        balance_after=inv.quantity - quantity,
        ref_type="TRANSFER", ref_id=t.id, ref_no=t.transfer_no,
        operator=operator, note=f"调往门店ID {to_store_id}，在途",
    ))
    db.flush()
    if commit:
        db.commit()
        db.refresh(t)
    return t


def receive_transfer(db: Session, *, transfer_id: int, operator: str,
                     when: datetime | None = None, commit: bool = True) -> Transfer:
    when = when or datetime.now()
    t = db.get(Transfer, transfer_id)
    if t is None:
        raise BizError("调拨单不存在", 404)
    if t.status != TransferStatus.IN_TRANSIT:
        raise BizError("该调拨单不在在途状态，不能重复收货")

    inv = _get_or_create_inventory(db, t.to_store_id, t.batch_id)
    inv.quantity += t.quantity
    t.status = TransferStatus.RECEIVED
    t.received_at = when
    t.received_by = operator
    db.add(StockLedger(
        ts=when, store_id=t.to_store_id, batch_id=t.batch_id,
        change_type=LedgerType.TRANSFER_IN, qty_change=t.quantity,
        balance_after=inv.quantity,
        ref_type="TRANSFER", ref_id=t.id, ref_no=t.transfer_no,
        operator=operator, note=f"来自门店ID {t.from_store_id} 的调拨收货",
    ))
    db.flush()
    if commit:
        db.commit()
        db.refresh(t)
    return t
