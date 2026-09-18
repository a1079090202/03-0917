"""模块二：效期锁定。

职责（只管效期，不管别的）：
- 过了有效期的批次整批锁死（EXPIRED_LOCKED，终态，系统内没有任何解锁入口）；
- 近效期判定：效期前 6 个月内的正常批次标记为近效期；
- 出库、调拨、召回、报表等入口在动账前都会先调用 apply_expiry_locks，
  保证"过期即锁"不依赖人工巡检。
"""
import calendar
from datetime import date, datetime

from sqlalchemy.orm import Session

from ..config import NEAR_EXPIRY_MONTHS
from ..models import Batch, BatchStatus, LedgerType, StockLedger


def add_months(d: date, months: int) -> date:
    m = d.month - 1 + months
    y = d.year + m // 12
    m = m % 12 + 1
    day = min(d.day, calendar.monthrange(y, m)[1])
    return date(y, m, day)


def is_expired(batch: Batch, on_date: date) -> bool:
    """有效期至 expiry_date 当天仍可用，次日即过期。"""
    return batch.expiry_date < on_date


def is_near_expiry(batch: Batch, on_date: date) -> bool:
    """正常在售且效期在 6 个月预警窗内。"""
    return (
        batch.status == BatchStatus.NORMAL
        and not is_expired(batch, on_date)
        and batch.expiry_date <= add_months(on_date, NEAR_EXPIRY_MONTHS)
    )


def apply_expiry_locks(db: Session, on_date: date | None = None) -> list[Batch]:
    """把所有已过有效期的批次置为 EXPIRED_LOCKED 并留流水。返回本次新锁定的批次。"""
    on_date = on_date or date.today()
    expired = (
        db.query(Batch)
        .filter(Batch.status != BatchStatus.EXPIRED_LOCKED, Batch.expiry_date < on_date)
        .all()
    )
    now = datetime.now()
    for b in expired:
        b.status = BatchStatus.EXPIRED_LOCKED
        b.expired_locked_at = now
        db.add(StockLedger(
            ts=now, store_id=None, batch_id=b.id,
            change_type=LedgerType.EXPIRY_LOCK, qty_change=0, balance_after=None,
            ref_type="SYSTEM", ref_id=None, ref_no="",
            operator="系统",
            note=f"超过有效期 {b.expiry_date.isoformat()}，整批自动锁死，禁止出库调拨",
        ))
    if expired:
        db.flush()
    return expired
