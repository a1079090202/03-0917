"""模块三：召回追溯。

输入批号，一口气给出：
- 该批总入库量；
- 发过哪些门店、各门店卖了多少、还剩多少；
- 总仓还剩多少；
- 调拨在途压在哪（哪张调拨单、从哪到哪、多少）；
- 对账：总入库 = 各点在库合计 + 已售合计 + 在途合计，不平即报警。
"""
from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import (Batch, Drug, InboundItem, Inventory, OrderType,
                      OutboundItem, OutboundOrder, Store, Transfer,
                      TransferStatus)
from .common import BizError
from .expiry_lock import apply_expiry_locks


def trace_batch(db: Session, *, batch_no: str, drug_id: int | None = None) -> dict:
    apply_expiry_locks(db, date.today())

    q = db.query(Batch).filter(Batch.batch_no == batch_no.strip())
    if drug_id:
        q = q.filter(Batch.drug_id == drug_id)
    batches = q.all()
    if not batches:
        raise BizError(f"未找到批号 {batch_no}", 404)
    if len(batches) > 1:
        raise BizError(f"批号 {batch_no} 对应多个药品的批次，请同时指定药品", 409)
    batch = batches[0]
    drug = db.get(Drug, batch.drug_id)

    total_inbound = (
        db.query(func.coalesce(func.sum(InboundItem.quantity), 0))
        .filter(InboundItem.batch_id == batch.id).scalar()
    )

    stores = db.query(Store).order_by(Store.id).all()
    locations = []
    total_on_hand = total_sold = 0
    for store in stores:
        on_hand = (
            db.query(func.coalesce(func.sum(Inventory.quantity), 0))
            .filter(Inventory.store_id == store.id, Inventory.batch_id == batch.id).scalar()
        )
        sold = (
            db.query(func.coalesce(func.sum(OutboundItem.quantity), 0))
            .join(OutboundOrder, OutboundItem.order_id == OutboundOrder.id)
            .filter(OutboundOrder.store_id == store.id, OutboundItem.batch_id == batch.id)
            .scalar()
        )
        split_sold = (
            db.query(func.coalesce(func.sum(OutboundItem.quantity), 0))
            .join(OutboundOrder, OutboundItem.order_id == OutboundOrder.id)
            .filter(OutboundOrder.store_id == store.id,
                    OutboundItem.batch_id == batch.id,
                    OutboundOrder.order_type == OrderType.SPLIT_SALE)
            .scalar()
        )
        transferred_in = (
            db.query(func.coalesce(func.sum(Transfer.quantity), 0))
            .filter(Transfer.to_store_id == store.id, Transfer.batch_id == batch.id,
                    Transfer.status == TransferStatus.RECEIVED).scalar()
        )
        transferred_out = (
            db.query(func.coalesce(func.sum(Transfer.quantity), 0))
            .filter(Transfer.from_store_id == store.id, Transfer.batch_id == batch.id,
                    Transfer.status.in_([TransferStatus.RECEIVED, TransferStatus.IN_TRANSIT]))
            .scalar()
        )
        if on_hand or sold or transferred_in or transferred_out:
            locations.append({
                "store_id": store.id,
                "store_name": store.name,
                "is_warehouse": store.is_warehouse,
                "on_hand": on_hand,
                "sold": sold,
                "split_sold": split_sold,
                "transferred_in": transferred_in,
                "transferred_out": transferred_out,
            })
        total_on_hand += on_hand
        total_sold += sold

    in_transit_rows = (
        db.query(Transfer)
        .filter(Transfer.batch_id == batch.id, Transfer.status == TransferStatus.IN_TRANSIT)
        .all()
    )
    store_names = {s.id: s.name for s in stores}
    in_transit = [{
        "transfer_no": t.transfer_no,
        "from_store": store_names.get(t.from_store_id, "?"),
        "to_store": store_names.get(t.to_store_id, "?"),
        "quantity": t.quantity,
        "shipped_at": t.created_at.strftime("%Y-%m-%d %H:%M"),
        "operator": t.operator,
    } for t in in_transit_rows]
    total_in_transit = sum(t["quantity"] for t in in_transit)

    return {
        "batch": {
            "id": batch.id,
            "batch_no": batch.batch_no,
            "drug_name": drug.name,
            "drug_code": drug.code,
            "spec": drug.spec,
            "unit": drug.unit,
            "manufacturer": drug.manufacturer,
            "production_date": batch.production_date.isoformat(),
            "expiry_date": batch.expiry_date.isoformat(),
            "supplier": batch.supplier,
            "status": batch.status,
        },
        "total_inbound": total_inbound,
        "locations": locations,
        "in_transit": in_transit,
        "total_on_hand": total_on_hand,
        "total_sold": total_sold,
        "total_in_transit": total_in_transit,
        # 对账：入库总量必须等于 在库 + 已售 + 在途
        "reconciled": total_inbound == total_on_hand + total_sold + total_in_transit,
    }
