"""入库服务：一批一条，批号/生产日期/有效期至/数量/供应商五要素缺一不可
（缺字段在 schema 层即 422）；同药同批号再次入库时生产日期、有效期必须与台账一致。"""
from datetime import datetime
from typing import Iterable

from sqlalchemy.orm import Session

from ..models import (Batch, BatchStatus, InboundItem, InboundOrder, Inventory,
                      LedgerType, StockLedger)
from .common import BizError, gen_no
from .expiry_lock import apply_expiry_locks


def _get_or_create_inventory(db: Session, store_id: int, batch_id: int) -> Inventory:
    inv = (db.query(Inventory)
           .filter(Inventory.store_id == store_id, Inventory.batch_id == batch_id)
           .first())
    if inv is None:
        inv = Inventory(store_id=store_id, batch_id=batch_id, quantity=0)
        db.add(inv)
        db.flush()
    return inv


def create_inbound(db: Session, *, store_id: int, operator: str, items: Iterable,
                   note: str = "", when: datetime | None = None,
                   commit: bool = True) -> InboundOrder:
    when = when or datetime.now()
    apply_expiry_locks(db, when.date())

    order = InboundOrder(order_no=gen_no("IN", when), store_id=store_id,
                         operator=operator, note=note, created_at=when)
    db.add(order)
    db.flush()

    for item in items:
        if item.quantity <= 0:
            raise BizError("入库数量必须为正整数")
        if item.expiry_date <= item.production_date:
            raise BizError(f"批号 {item.batch_no}：有效期至必须晚于生产日期")
        if item.expiry_date < when.date():
            raise BizError(f"批号 {item.batch_no} 已过有效期（{item.expiry_date.isoformat()}），禁止入库")

        batch = (db.query(Batch)
                 .filter(Batch.drug_id == item.drug_id, Batch.batch_no == item.batch_no)
                 .first())
        if batch is None:
            batch = Batch(
                drug_id=item.drug_id, batch_no=item.batch_no,
                production_date=item.production_date, expiry_date=item.expiry_date,
                supplier=item.supplier, status=BatchStatus.NORMAL, created_at=when,
            )
            db.add(batch)
            db.flush()
        else:
            if (batch.production_date != item.production_date
                    or batch.expiry_date != item.expiry_date):
                raise BizError(
                    f"批号 {item.batch_no} 已入库过，生产日期/有效期与台账不一致，禁止重复入账"
                )

        inv = _get_or_create_inventory(db, store_id, batch.id)
        inv.quantity += item.quantity
        db.add(InboundItem(order_id=order.id, batch_id=batch.id,
                           quantity=item.quantity, supplier=item.supplier))
        db.add(StockLedger(
            ts=when, store_id=store_id, batch_id=batch.id,
            change_type=LedgerType.INBOUND, qty_change=item.quantity,
            balance_after=inv.quantity,
            ref_type="INBOUND", ref_id=order.id, ref_no=order.order_no,
            operator=operator, note=f"供应商：{item.supplier}",
        ))
    db.flush()
    if commit:
        db.commit()
        db.refresh(order)
    return order
