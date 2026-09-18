"""数据模型。

约定：
- 所有数量均为整数，按最小包装单位（盒/瓶/支）存储；
- 库存 quantity 有 CHECK(quantity >= 0) 兜底，数据库层面不允许负数；
- 批次状态机：NORMAL -> QC_SUSPENDED -> NORMAL（凭质检放行单）
               NORMAL / QC_SUSPENDED -> EXPIRED_LOCKED（终态，任何人不可解）。
"""
from datetime import date, datetime

from sqlalchemy import (Boolean, CheckConstraint, Date, DateTime, ForeignKey,
                        Integer, String, Text, UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class BatchStatus:
    NORMAL = "NORMAL"                  # 正常
    QC_SUSPENDED = "QC_SUSPENDED"      # 质检停售
    EXPIRED_LOCKED = "EXPIRED_LOCKED"  # 过期锁死（终态）


class OrderType:
    SALE = "SALE"              # 销售出库（整盒）
    SPLIT_SALE = "SPLIT_SALE"  # 拆零销售（另记拆零台账）


class TransferStatus:
    IN_TRANSIT = "IN_TRANSIT"  # 在途
    RECEIVED = "RECEIVED"      # 已收货
    CANCELLED = "CANCELLED"    # 已取消


class LedgerType:
    INBOUND = "INBOUND"              # 入库 +
    SALE = "SALE"                    # 销售出库 -
    SPLIT_SALE = "SPLIT_SALE"        # 拆零出库 -
    TRANSFER_OUT = "TRANSFER_OUT"    # 调拨出 -
    TRANSFER_IN = "TRANSFER_IN"      # 调拨入 +
    EXPIRY_LOCK = "EXPIRY_LOCK"      # 过期锁死（数量不变，仅留痕）
    QC_SUSPEND = "QC_SUSPEND"        # 质检停售（仅留痕）
    QC_RELEASE = "QC_RELEASE"        # 质检放行（仅留痕）


class Drug(Base):
    __tablename__ = "drugs"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128), index=True)
    spec: Mapped[str] = mapped_column(String(128))          # 规格，如 0.25g×24粒/盒
    unit: Mapped[str] = mapped_column(String(16))           # 最小包装单位：盒/瓶/支
    manufacturer: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class Store(Base):
    __tablename__ = "stores"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(128))
    is_warehouse: Mapped[bool] = mapped_column(Boolean, default=False)


class Batch(Base):
    __tablename__ = "batches"
    __table_args__ = (UniqueConstraint("drug_id", "batch_no", name="uq_drug_batch"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    drug_id: Mapped[int] = mapped_column(ForeignKey("drugs.id"), index=True)
    batch_no: Mapped[str] = mapped_column(String(64), index=True)
    production_date: Mapped[date] = mapped_column(Date)
    expiry_date: Mapped[date] = mapped_column(Date, index=True)
    supplier: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(20), default=BatchStatus.NORMAL, index=True)
    qc_reason: Mapped[str | None] = mapped_column(Text, nullable=True)        # 停售原因
    qc_release_no: Mapped[str | None] = mapped_column(String(64), nullable=True)  # 最近一张放行单号
    qc_suspended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    qc_released_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expired_locked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class Inventory(Base):
    """某门店/总仓持有的某批次数量。"""
    __tablename__ = "inventory"
    __table_args__ = (
        UniqueConstraint("store_id", "batch_id", name="uq_store_batch"),
        CheckConstraint("quantity >= 0", name="ck_inventory_nonneg"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), index=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.id"), index=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class InboundOrder(Base):
    __tablename__ = "inbound_orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_no: Mapped[str] = mapped_column(String(40), unique=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"))
    operator: Mapped[str] = mapped_column(String(64))
    note: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class InboundItem(Base):
    __tablename__ = "inbound_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("inbound_orders.id"), index=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.id"), index=True)
    quantity: Mapped[int] = mapped_column(Integer)
    supplier: Mapped[str] = mapped_column(String(128))


class OutboundOrder(Base):
    __tablename__ = "outbound_orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_no: Mapped[str] = mapped_column(String(40), unique=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"))
    order_type: Mapped[str] = mapped_column(String(16), default=OrderType.SALE)
    operator: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class OutboundItem(Base):
    __tablename__ = "outbound_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("outbound_orders.id"), index=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.id"), index=True)
    quantity: Mapped[int] = mapped_column(Integer)


class Transfer(Base):
    __tablename__ = "transfers"
    id: Mapped[int] = mapped_column(primary_key=True)
    transfer_no: Mapped[str] = mapped_column(String(40), unique=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.id"), index=True)
    from_store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"))
    to_store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"))
    quantity: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default=TransferStatus.IN_TRANSIT, index=True)
    operator: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    received_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    received_by: Mapped[str | None] = mapped_column(String(64), nullable=True)


class StockLedger(Base):
    """库存流水：每动一批必留一条。qty_change 带符号，balance_after 为动后该店该批结存。"""
    __tablename__ = "stock_ledger"
    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)
    store_id: Mapped[int | None] = mapped_column(ForeignKey("stores.id"), nullable=True, index=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.id"), index=True)
    change_type: Mapped[str] = mapped_column(String(20), index=True)
    qty_change: Mapped[int] = mapped_column(Integer, default=0)
    balance_after: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ref_type: Mapped[str] = mapped_column(String(20), default="")   # INBOUND/OUTBOUND/TRANSFER/QC
    ref_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ref_no: Mapped[str] = mapped_column(String(40), default="")
    operator: Mapped[str] = mapped_column(String(64), default="")
    note: Mapped[str] = mapped_column(String(255), default="")


class SplitRecord(Base):
    """拆零台账：拆零销售单独记账，不与整盒销售混一笔。"""
    __tablename__ = "split_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), index=True)
    drug_id: Mapped[int] = mapped_column(ForeignKey("drugs.id"), index=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.id"), index=True)
    quantity: Mapped[int] = mapped_column(Integer)   # 拆零数量（最小包装单位）
    operator: Mapped[str] = mapped_column(String(64))
    outbound_order_id: Mapped[int] = mapped_column(ForeignKey("outbound_orders.id"))


class QCRecord(Base):
    """质检记录：停售 / 放行（放行必须挂放行单号）。"""
    __tablename__ = "qc_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.id"), index=True)
    action: Mapped[str] = mapped_column(String(16))   # SUSPEND / RELEASE
    reason: Mapped[str] = mapped_column(Text, default="")
    release_doc_no: Mapped[str | None] = mapped_column(String(64), nullable=True)
    operator: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
