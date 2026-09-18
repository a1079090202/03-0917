"""请求模型：入库五要素（批号/生产日期/有效期至/数量/供应商）在此强制，缺一样 422。"""
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class DrugIn(BaseModel):
    code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=128)
    spec: str = Field(min_length=1, max_length=128)
    unit: str = Field(min_length=1, max_length=16)
    manufacturer: str = Field(default="", max_length=128)


class InboundItemIn(BaseModel):
    drug_id: int
    batch_no: str = Field(min_length=1, max_length=64)
    production_date: date
    expiry_date: date
    quantity: int = Field(gt=0)
    supplier: str = Field(min_length=1, max_length=128)


class InboundIn(BaseModel):
    store_id: int
    operator: str = Field(min_length=1, max_length=64)
    note: str = Field(default="", max_length=255)
    items: list[InboundItemIn] = Field(min_length=1)


class AllocationIn(BaseModel):
    batch_id: int
    quantity: int = Field(gt=0)


class OutboundItemIn(BaseModel):
    drug_id: int
    quantity: int = Field(gt=0)
    allocations: list[AllocationIn] | None = None  # 不填 = 系统按效期自动分配


class OutboundIn(BaseModel):
    store_id: int
    order_type: Literal["SALE", "SPLIT_SALE"] = "SALE"
    operator: str = Field(min_length=1, max_length=64)
    items: list[OutboundItemIn] = Field(min_length=1)


class PreviewIn(BaseModel):
    store_id: int
    drug_id: int
    quantity: int = Field(gt=0)


class TransferIn(BaseModel):
    from_store_id: int
    to_store_id: int
    batch_id: int
    quantity: int = Field(gt=0)
    operator: str = Field(min_length=1, max_length=64)


class ReceiveIn(BaseModel):
    operator: str = Field(min_length=1, max_length=64)


class SuspendIn(BaseModel):
    reason: str = Field(min_length=1)
    operator: str = Field(min_length=1, max_length=64)


class ReleaseIn(BaseModel):
    release_doc_no: str = Field(default="", max_length=64)
    operator: str = Field(min_length=1, max_length=64)
