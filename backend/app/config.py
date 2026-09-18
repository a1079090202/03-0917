"""应用配置。所有路径都相对项目根目录，启动器双击运行也能定位。"""
import os
from pathlib import Path

# backend/app/config.py -> backend/ -> 项目根
BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("PHARMA_DATA_DIR", BASE_DIR / "data"))
STATIC_DIR = BASE_DIR / "frontend_dist"

DATA_DIR.mkdir(exist_ok=True)

DB_PATH = Path(os.environ.get("PHARMA_DB", DATA_DIR / "pharma.db"))
DB_URL = f"sqlite:///{DB_PATH.as_posix()}"

# 效期前 6 个月进入近效期预警
NEAR_EXPIRY_MONTHS = 6
# 并发条件更新撞写锁时的重试次数
BUSY_RETRY = 50
