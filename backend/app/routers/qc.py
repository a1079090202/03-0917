"""质检路由：停售 / 放行。"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas import ReleaseIn, SuspendIn
from ..services import qc as qc_svc

router = APIRouter(prefix="/api/batches", tags=["qc"])


@router.post("/{batch_id}/suspend")
def suspend(batch_id: int, payload: SuspendIn, db: Session = Depends(get_db)):
    batch = qc_svc.suspend_batch(db, batch_id=batch_id, reason=payload.reason,
                                 operator=payload.operator)
    return {"id": batch.id, "status": batch.status}


@router.post("/{batch_id}/release")
def release(batch_id: int, payload: ReleaseIn, db: Session = Depends(get_db)):
    batch = qc_svc.release_batch(db, batch_id=batch_id,
                                 release_doc_no=payload.release_doc_no,
                                 operator=payload.operator)
    return {"id": batch.id, "status": batch.status, "qc_release_no": batch.qc_release_no}
