"""质检服务：停售与放行。

- 判不合格：整批停售（QC_SUSPENDED），立即禁止出库、调拨；
- 恢复销售：必须挂质检放行单号，空单号一律拒 —— 口头说放了不算；
- 已过期锁死的批次：不能停售（已是终态），更永远不能放行，谁也解不开。
"""
from datetime import datetime

from sqlalchemy.orm import Session

from ..models import (Batch, BatchStatus, LedgerType, QCRecord, StockLedger)
from .common import BizError
from .expiry_lock import apply_expiry_locks


def suspend_batch(db: Session, *, batch_id: int, reason: str, operator: str,
                  when: datetime | None = None, commit: bool = True) -> Batch:
    when = when or datetime.now()
    apply_expiry_locks(db, when.date())
    batch = db.get(Batch, batch_id)
    if batch is None:
        raise BizError("批次不存在", 404)
    if batch.status == BatchStatus.EXPIRED_LOCKED:
        raise BizError("该批已过有效期，已锁死（终态），无需再停售")
    if batch.status == BatchStatus.QC_SUSPENDED:
        raise BizError("该批已处于质检停售状态")
    if not reason.strip():
        raise BizError("停售必须填写原因")

    batch.status = BatchStatus.QC_SUSPENDED
    batch.qc_reason = reason
    batch.qc_suspended_at = when
    db.add(QCRecord(batch_id=batch_id, action="SUSPEND", reason=reason,
                    operator=operator, created_at=when))
    db.add(StockLedger(
        ts=when, store_id=None, batch_id=batch_id,
        change_type=LedgerType.QC_SUSPEND, qty_change=0, balance_after=None,
        ref_type="QC", ref_id=None, ref_no="",
        operator=operator, note=f"质检停售：{reason}",
    ))
    db.flush()
    if commit:
        db.commit()
        db.refresh(batch)
    return batch


def release_batch(db: Session, *, batch_id: int, release_doc_no: str, operator: str,
                  when: datetime | None = None, commit: bool = True) -> Batch:
    when = when or datetime.now()
    apply_expiry_locks(db, when.date())
    batch = db.get(Batch, batch_id)
    if batch is None:
        raise BizError("批次不存在", 404)
    if batch.status == BatchStatus.EXPIRED_LOCKED or batch.expiry_date < when.date():
        raise BizError("该批已过有效期，锁死为终态，任何人不可放行")
    if batch.status != BatchStatus.QC_SUSPENDED:
        raise BizError("该批不在停售状态，无需放行")
    if not release_doc_no or not release_doc_no.strip():
        raise BizError("恢复销售必须填写质检放行单号，口头放行无效")

    batch.status = BatchStatus.NORMAL
    batch.qc_release_no = release_doc_no.strip()
    batch.qc_released_at = when
    db.add(QCRecord(batch_id=batch_id, action="RELEASE", reason="",
                    release_doc_no=release_doc_no.strip(),
                    operator=operator, created_at=when))
    db.add(StockLedger(
        ts=when, store_id=None, batch_id=batch_id,
        change_type=LedgerType.QC_RELEASE, qty_change=0, balance_after=None,
        ref_type="QC", ref_id=None, ref_no=release_doc_no.strip(),
        operator=operator, note=f"凭质检放行单 {release_doc_no.strip()} 恢复销售",
    ))
    db.flush()
    if commit:
        db.commit()
        db.refresh(batch)
    return batch
