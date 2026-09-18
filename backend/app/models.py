"""数据库模型。

铁律：
- 所有数量一律存【最小包装单位】的非负整数（CHECK qty>=0）；
- 批次状态只有 正常/停售 两种，过期不入库存状态，按效期日期当天自动锁死，谁也改不了；
- 库存按 批次×货位 记账，总仓和 8 家门店各自一行。
"""
from datetime import date

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


# ---- 枚举常量（字符串入库，便于读账） ----
LOC_WAREHOUSE = "warehouse"
LOC_STORE = "store"

BATCH_NORMAL = "normal"
BATCH_HOLD = "hold"  # 质检不合格、整批停售

OUT_SALE = "sale"    # 整包装销售出库
OUT_SPLIT = "split"  # 拆零销售出库（另记拆零台账）

TRANSIT = "in_transit"
RECEIVED = "received"

QUALITY_HOLD = "hold"
QUALITY_RELEASE = "release"


class Base(DeclarativeBase):
    pass


class Drug(Base):
    __tablename__ = "drug"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)          # 国药准字/自编编码
    name: Mapped[str] = mapped_column(String(128))
    spec: Mapped[str] = mapped_column(String(128))                      # 规格
    manufacturer: Mapped[str] = mapped_column(String(128))
    unit: Mapped[str] = mapped_column(String(16))                       # 最小包装单位（支/片/袋…）
    bulk_unit: Mapped[str | None] = mapped_column(String(16))           # 零售大包装单位（盒）
    bulk_size: Mapped[int | None] = mapped_column(Integer)              # 1 大包装 = 多少最小单位

    batches: Mapped[list["Batch"]] = relationship(back_populates="drug")


class Location(Base):
    __tablename__ = "location"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(16), unique=True)          # WH / S01..S08
    name: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(16))                       # warehouse / store


class Batch(Base):
    __tablename__ = "batch"
    __table_args__ = (UniqueConstraint("drug_id", "batch_no", name="uq_batch_drug_no"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    drug_id: Mapped[int] = mapped_column(ForeignKey("drug.id"))
    batch_no: Mapped[str] = mapped_column(String(64))                   # 厂家批号
    production_date: Mapped[date] = mapped_column(Date)
    expiry_date: Mapped[date] = mapped_column(Date)                     # 有效期至（当天仍可售，次日锁死）
    supplier: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(16), default=BATCH_NORMAL)
    created_at: Mapped[date] = mapped_column(Date)

    drug: Mapped[Drug] = relationship(back_populates="batches")
    stocks: Mapped[list["Stock"]] = relationship(back_populates="batch")


class Stock(Base):
    """批次×货位库存，数量为最小包装单位的非负整数。"""
    __tablename__ = "stock"
    __table_args__ = (
        UniqueConstraint("batch_id", "location_id", name="uq_stock_batch_loc"),
        CheckConstraint("qty >= 0", name="ck_stock_qty_nonneg"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batch.id"))
    location_id: Mapped[int] = mapped_column(ForeignKey("location.id"))
    qty: Mapped[int] = mapped_column(Integer, default=0)

    batch: Mapped[Batch] = relationship(back_populates="stocks")


class Inbound(Base):
    """入库一条：批号/生产日期/有效期至/数量/供应商缺一不进账。"""
    __tablename__ = "inbound"

    id: Mapped[int] = mapped_column(primary_key=True)
    no: Mapped[str] = mapped_column(String(32), unique=True)            # 入库单号
    batch_id: Mapped[int] = mapped_column(ForeignKey("batch.id"))
    drug_id: Mapped[int] = mapped_column(ForeignKey("drug.id"))
    qty: Mapped[int] = mapped_column(Integer)
    supplier: Mapped[str] = mapped_column(String(128))
    production_date: Mapped[date] = mapped_column(Date)
    expiry_date: Mapped[date] = mapped_column(Date)
    operator: Mapped[str] = mapped_column(String(32), default="仓管员")
    created_at: Mapped[date] = mapped_column(DateTime)
    note: Mapped[str | None] = mapped_column(String(255))


class Outbound(Base):
    """出库单头：一次出库可能按 FEFO 动多个批次，明细见 OutboundFlow。"""
    __tablename__ = "outbound"

    id: Mapped[int] = mapped_column(primary_key=True)
    no: Mapped[str] = mapped_column(String(32), unique=True)
    drug_id: Mapped[int] = mapped_column(ForeignKey("drug.id"))
    location_id: Mapped[int] = mapped_column(ForeignKey("location.id"))
    qty: Mapped[int] = mapped_column(Integer)                           # 总数量（最小单位）
    kind: Mapped[str] = mapped_column(String(16))                       # sale / split
    operator: Mapped[str] = mapped_column(String(32), default="营业员")
    created_at: Mapped["object"] = mapped_column(DateTime)
    note: Mapped[str | None] = mapped_column(String(255))

    flows: Mapped[list["OutboundFlow"]] = relationship(back_populates="outbound")


class OutboundFlow(Base):
    """出库流水：每动一个批次留一行，账永远对得上批次。"""
    __tablename__ = "outbound_flow"

    id: Mapped[int] = mapped_column(primary_key=True)
    outbound_id: Mapped[int] = mapped_column(ForeignKey("outbound.id"))
    batch_id: Mapped[int] = mapped_column(ForeignKey("batch.id"))
    location_id: Mapped[int] = mapped_column(ForeignKey("location.id"))
    qty: Mapped[int] = mapped_column(Integer)
    expiry_date: Mapped[date] = mapped_column(Date)                     # 记账时快照，防改期争议
    created_at: Mapped["object"] = mapped_column(DateTime)

    outbound: Mapped[Outbound] = relationship(back_populates="flows")


class SplitSale(Base):
    """拆零销售台账：整盒、零卖绝不混在一笔账里。"""
    __tablename__ = "split_sale"

    id: Mapped[int] = mapped_column(primary_key=True)
    outbound_id: Mapped[int] = mapped_column(ForeignKey("outbound.id"))
    batch_id: Mapped[int] = mapped_column(ForeignKey("batch.id"))
    location_id: Mapped[int] = mapped_column(ForeignKey("location.id"))
    qty: Mapped[int] = mapped_column(Integer)                           # 拆零售出最小单位数
    bulk_packages: Mapped[int] = mapped_column(Integer)                 # 折合整盒数（向下取整）
    loose_units: Mapped[int] = mapped_column(Integer)                  # 余下散卖单位
    created_at: Mapped["object"] = mapped_column(DateTime)


class Transfer(Base):
    """调拨单：门店间/总仓→门店。发货即入在途，收货才落门店库存。"""
    __tablename__ = "transfer"

    id: Mapped[int] = mapped_column(primary_key=True)
    no: Mapped[str] = mapped_column(String(32), unique=True)
    drug_id: Mapped[int] = mapped_column(ForeignKey("drug.id"))
    from_location_id: Mapped[int] = mapped_column(ForeignKey("location.id"))
    to_location_id: Mapped[int] = mapped_column(ForeignKey("location.id"))
    qty: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default=TRANSIT)
    operator: Mapped[str] = mapped_column(String(32), default="仓管员")
    shipped_at: Mapped["object"] = mapped_column(DateTime)
    received_at: Mapped["object | None"] = mapped_column(DateTime, nullable=True)

    items: Mapped[list["TransferItem"]] = relationship(back_populates="transfer")


class TransferItem(Base):
    """调拨按 FEFO 拆批留痕；在途量 = 未收货单的明细数。"""
    __tablename__ = "transfer_item"

    id: Mapped[int] = mapped_column(primary_key=True)
    transfer_id: Mapped[int] = mapped_column(ForeignKey("transfer.id"))
    batch_id: Mapped[int] = mapped_column(ForeignKey("batch.id"))
    qty: Mapped[int] = mapped_column(Integer)
    expiry_date: Mapped[date] = mapped_column(Date)

    transfer: Mapped[Transfer] = relationship(back_populates="items")


class QualityAction(Base):
    """质检动作：停售 / 放行。放行必须挂质检放行单号，口头放行不入账。"""
    __tablename__ = "quality_action"

    id: Mapped[int] = mapped_column(primary_key=True)
    no: Mapped[str] = mapped_column(String(32), unique=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batch.id"))
    action: Mapped[str] = mapped_column(String(16))                     # hold / release
    doc_no: Mapped[str | None] = mapped_column(String(64))             # 放行单号（放行必填）
    reason: Mapped[str | None] = mapped_column(String(255))
    operator: Mapped[str] = mapped_column(String(32), default="质检员")
    created_at: Mapped["object"] = mapped_column(DateTime)


class RecallNotice(Base):
    """厂家召回函登记。"""
    __tablename__ = "recall_notice"

    id: Mapped[int] = mapped_column(primary_key=True)
    no: Mapped[str] = mapped_column(String(32), unique=True)            # 召回函号
    batch_id: Mapped[int] = mapped_column(ForeignKey("batch.id"))
    issuer: Mapped[str] = mapped_column(String(128))                    # 发函厂家/供应商
    issued_date: Mapped[date] = mapped_column(Date)
    note: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped["object"] = mapped_column(DateTime)
