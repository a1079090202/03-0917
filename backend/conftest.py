"""pytest 公共装置：独立临时库 + 最小业务世界（总仓/门店/药品/两批次）。"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["PHARMACY_DB"] = os.path.join(tempfile.mkdtemp(prefix="pharmacy_test_"), "test.db")

import pytest  # noqa: E402


@pytest.fixture()
def db():
    from app.database import Base, SessionLocal, engine
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture()
def client(db):
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)


@pytest.fixture()
def world(db):
    """两门店一药两批：B1 效期近(2027-01-10)、B2 效期远(2028-06-10)，各在门店有货。"""
    from datetime import date
    from app.models import Drug, Store
    from app.services.inbound import create_inbound
    from app.services.transfers import create_transfer, receive_transfer
    from types import SimpleNamespace as NS

    wh = Store(code="WH", name="总仓", is_warehouse=True)
    s1 = Store(code="S01", name="一店", is_warehouse=False)
    db.add_all([wh, s1])
    db.flush()
    drug = Drug(code="T001", name="测试药", spec="10mg×10片/盒", unit="盒", manufacturer="测试厂")
    db.add(drug)
    db.flush()

    def inbound(batch_no, exp, qty):
        item = NS(drug_id=drug.id, batch_no=batch_no, production_date=date(2026, 1, 1),
                  expiry_date=exp, quantity=qty, supplier="测试供应商")
        create_inbound(db, store_id=wh.id, operator="测试员", items=[item])

    def to_store(batch_no, qty):
        from app.models import Batch
        b = db.query(Batch).filter(Batch.batch_no == batch_no).one()
        t = create_transfer(db, from_store_id=wh.id, to_store_id=s1.id,
                            batch_id=b.id, quantity=qty, operator="测试员")
        receive_transfer(db, transfer_id=t.id, operator="测试员")

    inbound("B1", date(2027, 1, 10), 100)
    inbound("B2", date(2028, 6, 10), 100)
    to_store("B1", 50)
    to_store("B2", 50)

    from app.models import Batch
    b1 = db.query(Batch).filter(Batch.batch_no == "B1").one()
    b2 = db.query(Batch).filter(Batch.batch_no == "B2").one()
    db.commit()  # 释放写锁：BEGIN IMMEDIATE 下，敞开的会话会挡住其他连接的写事务
    return {"wh": wh, "store": s1, "drug": drug, "b1": b1, "b2": b2}
