"""召回追溯路由。"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..services import recall as recall_svc

router = APIRouter(prefix="/api/recall", tags=["recall"])


@router.get("/trace")
def trace(batch_no: str = Query(..., min_length=1),
          drug_id: int | None = None,
          db: Session = Depends(get_db)):
    return recall_svc.trace_batch(db, batch_no=batch_no, drug_id=drug_id)
