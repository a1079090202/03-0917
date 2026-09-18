"""全局配置：路径、数据库位置、效期规则常量。"""
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # backend/
ROOT_DIR = os.path.dirname(BASE_DIR)                                     # 项目根
DATA_DIR = os.path.join(ROOT_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

DB_PATH = os.environ.get("PHARMACY_DB", os.path.join(DATA_DIR, "pharmacy.db"))
DATABASE_URL = f"sqlite:///{DB_PATH}"

STATIC_DIR = os.path.join(BASE_DIR, "app", "static")

# 近效期预警窗口：效期前 6 个月
NEAR_EXPIRY_MONTHS = 6

# 服务端口（.bat 启动器使用）
PORT = int(os.environ.get("PHARMACY_PORT", "8000"))
