"""效期服务：近效期标记与过期锁死的唯一判定口径。

口径写死在这里，全系统任何出库/调拨/收货都只认这一个函数：
- expiry_date 当天仍可售（"有效期至 2026-09-18" 指当天有效）；
- 次日 0 点起整批锁死，没有任何状态字段、任何角色可以解开；
- 距到期日 <= 6 个月（183 天口径）标近效期。
"""
from datetime import date, timedelta

from ..config import NEAR_EXPIRY_MONTHS
from ..models import Batch, BATCH_HOLD

# 近效期按 6 个自然月算（与药房习惯一致，不按 180 天硬数）
_SIX_MONTH_DAYS = 183


def is_expired(batch: Batch, today: date | None = None) -> bool:
    today = today or date.today()
    return batch.expiry_date < today


def is_near_expiry(batch: Batch, today: date | None = None) -> bool:
    today = today or date.today()
    if is_expired(batch, today):
        return False
    return batch.expiry_date <= today + timedelta(days=_SIX_MONTH_DAYS)


def block_reason(batch: Batch, today: date | None = None) -> str | None:
    """返回批次不能出库的原因；能出则返回 None。过期优先于停售提示。"""
    if is_expired(batch, today):
        return f"批次已于 {batch.expiry_date} 到期，系统锁死，禁止出库（任何人不可解锁）"
    if batch.status == BATCH_HOLD:
        return "批次质检不合格处于停售状态，须凭质检放行单恢复"
    return None


def batch_flag(batch: Batch, today: date | None = None) -> str:
    """看板/台账上的状态标签。"""
    if is_expired(batch, today):
        return "expired"
    if batch.status == BATCH_HOLD:
        return "hold"
    if is_near_expiry(batch, today):
        return "near"
    return "normal"


def near_window_start(expiry: date, today: date) -> bool:
    """供报表用：该日期是否落在"距今 6 个月内"窗口。"""
    return expiry <= today + timedelta(days=_SIX_MONTH_DAYS)
