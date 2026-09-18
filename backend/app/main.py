"""FastAPI 应用装配：路由、业务异常处理、前端静态托管、启动时过期批锁定。"""
import os
from contextlib import asynccontextmanager
from datetime import date

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import STATIC_DIR
from .database import SessionLocal, init_db
from .routers import catalog, inbound, outbound, qc, recall, reports, splits, transfers
from .services.common import BizError
from .services.expiry_lock import apply_expiry_locks


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    db = SessionLocal()
    try:
        locked = apply_expiry_locks(db, date.today())
        db.commit()
        if locked:
            print(f"[效期锁定] 启动时锁死 {len(locked)} 个过期批次")
    finally:
        db.close()
    yield


app = FastAPI(title="连锁药房批号效期台账", version="1.0.0", lifespan=lifespan)


@app.exception_handler(BizError)
async def biz_error_handler(_: Request, exc: BizError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


for r in (catalog.router, inbound.router, outbound.router, transfers.router,
          qc.router, recall.router, reports.router, splits.router):
    app.include_router(r)


@app.get("/api/health")
def health():
    return {"ok": True}


# 前端构建产物托管（npm run build 输出到 app/static），门店浏览器直接打开即可
if os.path.isdir(STATIC_DIR):
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
