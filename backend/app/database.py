"""数据库连接。

并发安全三件套（库存扣减的地基）：
1. WAL 模式 —— 读写不互斥；
2. busy_timeout —— 写锁冲突时等待而非立刻报错；
3. BEGIN IMMEDIATE —— 事务一开始就拿到写锁，两个并发出库串行化，
   配合库存扣减的条件更新（UPDATE ... WHERE quantity >= ?），
   从机制上保证：最后一批两个人同时出，只有一个成功，账上永不出现负数。
"""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import DATABASE_URL


class Base(DeclarativeBase):
    pass


engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_conn, _):
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA busy_timeout=10000")
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.close()


@event.listens_for(engine, "begin")
def _begin_immediate(conn):
    # 所有事务以 BEGIN IMMEDIATE 开始：进事务即持写锁，并发写串行化，
    # 杜绝"两个事务都读到旧库存、都扣成功"的超卖窗口。
    conn.exec_driver_sql("BEGIN IMMEDIATE")


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db():
    from . import models  # noqa: F401  确保模型已注册
    Base.metadata.create_all(engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
