"""SQLAlchemy 引擎与会话。

SQLite 并发关键设置：
- WAL 日志：读不阻塞写、写不阻塞读；
- busy_timeout：两个写事务撞锁时等待而不是立刻报 database is locked；
- foreign_keys=ON：批次库存等外键约束真正生效；
- 每个请求一个独立连接/会话，两个浏览器窗口的出库事务互相隔离。
"""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from .config import DB_URL

engine = create_engine(
    DB_URL,
    connect_args={"timeout": 30, "check_same_thread": False},
    future=True,
)


@event.listens_for(engine, "connect")
def _sqlite_pragmas(dbapi_conn, _):
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA busy_timeout=30000")
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
