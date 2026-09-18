"""Pydantic 入参/出参模型。入库五要素在类型层就缺一不可。"""
from datetime import date

from pydantic import BaseModel, Field, field_validator


# ---------------- 基础档案 ----------------
class DrugOut(BaseModel):
    id: int
    code: str
    name: str
    spec: str
    manufacturer: str
    unit: str
    bulk_unit: str | None = None
    bulk_size: int | None = None

    model_config = {"from_attributes": True}


class LocationOut(BaseModel):
    id: int
    code: str
    name: str
    kind: str

    model_config = {"from_attributes": True}


# ---------------- 入库 ----------------
class InboundIn(BaseModel):
    # 批号、生产日期、有效期至、数量、供应商——五样一个都不能少
    drug_id: int
    batch_no: str = Field(min_length=1)
    production_date: date
    expiry_date: date
    qty: int = Field(gt=0)
    supplier: str = Field(min_length=1)
    operator: str = "仓管员"
    note: str | None = None

    @field_validator("qty")
    @classmethod
    def _int_unit(cls, v):
        if not isinstance(v, int):
            raise ValueError("数量必须是最小包装单位整数")
        return v


# ---------------- 出库 ----------------
class OutboundIn(BaseModel):
    drug_id: int
    location_id: int
    qty: int = Field(gt=0)
    kind: str = "sale"  # sale 整包装 / split 拆零
    operator: str = "营业员"
    note: str | None = None
    # 仅用于验收 FEFO：前端若指定批次，必须是 FEFO 第一顺位，否则判违规
    requested_batch_id: int | None = None

    @field_validator("kind")
    @classmethod
    def _kind(cls, v):
        if v not in ("sale", "split"):
            raise ValueError("kind 只能是 sale 或 split")
        return v


class PreviewIn(BaseModel):
    drug_id: int
    location_id: int
    qty: int = Field(gt=0)


# ---------------- 调拨 ----------------
class TransferShipIn(BaseModel):
    drug_id: int
    from_location_id: int
    to_location_id: int
    qty: int = Field(gt=0)
    operator: str = "仓管员"


class TransferReceiveIn(BaseModel):
    operator: str = "门店收货员"


# ---------------- 质检 ----------------
class HoldIn(BaseModel):
    batch_id: int
    reason: str = Field(min_length=1)
    operator: str = "质检员"


class ReleaseIn(BaseModel):
    batch_id: int
    doc_no: str = Field(min_length=1)  # 质检放行单号，必填
    reason: str | None = None
    operator: str = "质检员"


# ---------------- 召回 ----------------
class RecallIn(BaseModel):
    batch_id: int
    no: str = Field(min_length=1)
    issuer: str = Field(min_length=1)
    issued_date: date
    note: str | None = None
