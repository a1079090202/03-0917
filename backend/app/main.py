"""FastAPI 主入口。

前端 Vue3 构建产物放在 frontend_dist/，由本服务直接托管，
总仓/门店浏览器只访问 http://<总仓电脑IP>:8000 一个地址即可。
"""
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import STATIC_DIR
from .routers import ops, stock

app = FastAPI(title="批号效期台账", version="1.0")

app.include_router(stock.router)
app.include_router(ops.router)


@app.get("/api/health")
def health():
    return {"ok": True}


# 静态资源（js/css）与 SPA 回退必须挂在 /api 路由之后
if STATIC_DIR.exists():
    app.mount(
        "/assets",
        StaticFiles(directory=STATIC_DIR / "assets"),
        name="assets",
    )

    @app.get("/")
    def index():
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str):
        # /api 下未命中的路径不做回退
        if full_path.startswith("api/"):
            return {"detail": "Not Found"}
        candidate = STATIC_DIR / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(STATIC_DIR / "index.html")
else:
    @app.get("/")
    def no_frontend():
        return {
            "msg": "后端已启动，但前端尚未构建。请先运行 build_frontend.bat 或执行 "
                   "npm install && npm run build（详见交付说明）。",
            "docs": "/docs",
        }
