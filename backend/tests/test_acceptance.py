"""验收测试：对应老板亲自验的五件事，外加入库校验、质检放行、调拨留痕。

1. 两个窗口同时对同一批出库 —— 不卖穿、不负数；
2. 过期批、停售批下出库单 —— 拦得住；
3. 故意先出效期远的批 —— 系统不认；
4. 输批号跑召回 —— 流向对得上数；
5. 上月报表 —— 跟台账对得平。
"""
import threading
from datetime import date, datetime
from types import SimpleNamespace as NS

import pytest

from app.models import (Batch, BatchStatus, Inventory, OrderType, SplitRecord,
                        StockLedger, Store, Transfer, TransferStatus)
from app.services.common import BizError
from app.services.inbound import create_inbound
from app.services.outbound import create_outbound
from app.services.qc import release_batch, suspend_batch
from app.services.recall import trace_batch
from app.services.reports import monthly_flow, near_expiry_report
from app.services.transfers import create_transfer, receive_transfer


def _item(drug_id, qty, allocations=None):
    return NS(drug_id=drug_id, quantity=qty, allocations=allocations)


def _stock(db, store_id, batch_id):
    inv = db.query(Inventory).filter(
        Inventory.store_id == store_id, Inventory.batch_id == batch_id).first()
    return inv.quantity if inv else 0


# ---------- 1. 并发：两人同时出最后一批，不卖穿 ----------

def test_concurrent_outbound_never_oversells(db, world):
    """门店该药两批共 100 盒，12 个线程各抢 10 盒：成功总数必须等于 100，两批归零不负。"""
    store, drug, b1, b2 = world["store"], world["drug"], world["b1"], world["b2"]
    from app.database import SessionLocal
    results, errors = [], []

    def worker():
        s = SessionLocal()
        try:
            create_outbound(s, store_id=store.id, order_type=OrderType.SALE,
                            operator="并发测试", items=[_item(drug.id, 10)])
            results.append(1)
        except BizError as e:
            errors.append(e.message)
            s.rollback()
        finally:
            s.close()

    threads = [threading.Thread(target=worker) for _ in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sum(results) * 10 == 100, f"成功扣减 {sum(results)*10}，应为 100"
    assert len(errors) == 2, "超出库存的 2 笔必须被拒"
    assert _stock(db, store.id, b1.id) == 0
    assert _stock(db, store.id, b2.id) == 0
    assert db.query(Inventory).filter(Inventory.quantity < 0).count() == 0


def test_outbound_insufficient_stock_rejected(db, world):
    store, drug = world["store"], world["drug"]
    with pytest.raises(BizError, match="可售库存不足"):
        create_outbound(db, store_id=store.id, order_type=OrderType.SALE,
                        operator="t", items=[_item(drug.id, 999)])


# ---------- 2. 过期批 / 停售批：拦得住 ----------

def test_expired_batch_locked_and_blocked(db, world):
    """把 B1 改成昨天过期：自动锁死，出库、调拨、放行全部拒。"""
    store, drug, b1 = world["store"], world["drug"], world["b1"]
    b1.expiry_date = date(2020, 1, 1)
    db.commit()

    with pytest.raises(BizError, match="可售库存不足"):  # 自动分配跳过过期批，B2 只有 50
        create_outbound(db, store_id=store.id, order_type=OrderType.SALE,
                        operator="t", items=[_item(drug.id, 60)])
    db.refresh(b1)
    assert b1.status == BatchStatus.EXPIRED_LOCKED

    with pytest.raises(BizError, match="已过有效期.*禁止出库"):
        create_outbound(db, store_id=store.id, order_type=OrderType.SALE,
                        operator="t", items=[_item(drug.id, 10, [NS(batch_id=b1.id, quantity=10)])])
    with pytest.raises(BizError, match="禁止调拨"):
        create_transfer(db, from_store_id=store.id, to_store_id=world["wh"].id,
                        batch_id=b1.id, quantity=1, operator="t")
    with pytest.raises(BizError, match="任何人不可放行|无需再停售"):
        release_batch(db, batch_id=b1.id, release_doc_no="QJ2026-001", operator="t")
    with pytest.raises(BizError, match="无需再停售|任何人不可放行"):
        suspend_batch(db, batch_id=b1.id, reason="x", operator="t")


def test_qc_suspended_blocked_until_release_with_doc(db, world):
    """停售批出不了库；放行必须挂放行单号，空单号拒；放行后恢复可售。"""
    store, drug, b1 = world["store"], world["drug"], world["b1"]
    suspend_batch(db, batch_id=b1.id, reason="抽检不合格", operator="质检")

    with pytest.raises(BizError, match="质检停售中，禁止出库"):
        create_outbound(db, store_id=store.id, order_type=OrderType.SALE,
                        operator="t", items=[_item(drug.id, 10, [NS(batch_id=b1.id, quantity=10)])])
    with pytest.raises(BizError, match="质检停售中，禁止调拨"):
        create_transfer(db, from_store_id=store.id, to_store_id=world["wh"].id,
                        batch_id=b1.id, quantity=1, operator="t")
    with pytest.raises(BizError, match="放行单号"):
        release_batch(db, batch_id=b1.id, release_doc_no="  ", operator="质检")

    release_batch(db, batch_id=b1.id, release_doc_no="QJ-FX-2026-001", operator="质检")
    db.refresh(b1)
    assert b1.status == BatchStatus.NORMAL
    assert b1.qc_release_no == "QJ-FX-2026-001"

    order = create_outbound(db, store_id=store.id, order_type=OrderType.SALE,
                            operator="t", items=[_item(drug.id, 10)])
    assert order.id  # 放行后 FEFO 又会先出 B1
    assert _stock(db, store.id, b1.id) == 40


# ---------- 3. FEFO：故意先出效期远的批，系统不认 ----------

def test_fefo_auto_allocation_nearest_expiry_first(db, world):
    """自动分配：先吃效期近的 B1，B1 不够才动 B2。"""
    store, drug, b1, b2 = world["store"], world["drug"], world["b1"], world["b2"]
    create_outbound(db, store_id=store.id, order_type=OrderType.SALE,
                    operator="t", items=[_item(drug.id, 60)])
    assert _stock(db, store.id, b1.id) == 0   # B1 50 盒全出
    assert _stock(db, store.id, b2.id) == 40  # 再从 B2 出 10


def test_manual_far_expiry_batch_rejected(db, world):
    """B1（效期近）还有货时指定出 B2（效期远）——必须拒，并点名应先出的批号。"""
    store, drug, b2 = world["store"], world["drug"], world["b2"]
    with pytest.raises(BizError, match="违反效期先出原则.*B1"):
        create_outbound(db, store_id=store.id, order_type=OrderType.SALE,
                        operator="t", items=[_item(drug.id, 10, [NS(batch_id=b2.id, quantity=10)])])


def test_manual_allocation_matching_fefo_accepted(db, world):
    """手工指定与 FEFO 一致（B1 出完再出 B2）则放行。"""
    store, drug, b1, b2 = world["store"], world["drug"], world["b1"], world["b2"]
    allocs = [NS(batch_id=b1.id, quantity=50), NS(batch_id=b2.id, quantity=10)]
    create_outbound(db, store_id=store.id, order_type=OrderType.SALE,
                    operator="t", items=[_item(drug.id, 60, allocs)])
    assert _stock(db, store.id, b1.id) == 0
    assert _stock(db, store.id, b2.id) == 40


# ---------- 4. 召回追溯：流向对得上数 ----------

def test_recall_trace_reconciles(db, world):
    """造一笔在途调拨后追溯 B1：总入库 = 各点在库 + 已售 + 在途。"""
    store, wh, drug, b1 = world["store"], world["wh"], world["drug"], world["b1"]
    create_outbound(db, store_id=store.id, order_type=OrderType.SALE,
                    operator="t", items=[_item(drug.id, 20)])
    create_transfer(db, from_store_id=store.id, to_store_id=wh.id,
                    batch_id=b1.id, quantity=10, operator="t")  # 在途不收

    t = trace_batch(db, batch_no="B1")
    assert t["total_inbound"] == 100
    assert t["total_sold"] == 20
    assert t["total_in_transit"] == 10
    assert t["total_on_hand"] == 70  # 总仓 50 + 门店 20
    assert t["reconciled"] is True
    assert any(loc["store_name"] == "一店" and loc["sold"] == 20 for loc in t["locations"])
    assert t["in_transit"][0]["to_store"] == "总仓"


def test_recall_unknown_batch_404(db):
    with pytest.raises(BizError, match="未找到批号"):
        trace_batch(db, batch_no="NOPE")


# ---------- 5. 月报：跟台账对得平 ----------

def test_monthly_flow_matches_ledger(db, world):
    """本月流向表：期初+入库+调入-销售-拆零-调出=期末，且与流水代数和一致。"""
    store, drug, b1 = world["store"], world["drug"], world["b1"]
    create_outbound(db, store_id=store.id, order_type=OrderType.SALE,
                    operator="t", items=[_item(drug.id, 20)])
    create_outbound(db, store_id=store.id, order_type=OrderType.SPLIT_SALE,
                    operator="t", items=[_item(drug.id, 5)])

    month = datetime.now().strftime("%Y-%m")
    rep = monthly_flow(db, month)
    row = next(r for r in rep["batches"] if r["batch_no"] == "B1")
    assert row["inbound"] == 100 and row["transfer_out"] == 50
    assert row["sale"] == 20 and row["split_sale"] == 5
    assert row["closing"] == row["opening"] + row["inbound"] + row["transfer_in"] \
        - row["sale"] - row["split_sale"] - row["transfer_out"]

    # 与流水直接对账：全链期末 = 流水代数和
    from sqlalchemy import func
    ledger_sum = db.query(func.sum(StockLedger.qty_change)).filter(
        StockLedger.batch_id == b1.id).scalar()
    assert row["closing"] == ledger_sum


def test_near_expiry_report_flags_window(db, world):
    month = datetime.now().strftime("%Y-%m")
    rep = near_expiry_report(db, month)
    nos = {i["batch_no"] for i in rep["items"]}
    assert "B1" in nos        # 2027-01-10 到期，在 6 个月窗内
    assert "B2" not in nos    # 2028-06-10 到期，不在窗内


# ---------- 入库五要素 / 重复入库一致性 ----------

def test_inbound_missing_fields_422(client, world):
    """少一样（这里缺供应商）直接 422，这批进不了账。"""
    resp = client.post("/api/inbound", json={
        "store_id": world["wh"].id, "operator": "t",
        "items": [{"drug_id": world["drug"].id, "batch_no": "B9",
                   "production_date": "2026-01-01", "expiry_date": "2028-01-01",
                   "quantity": 10}],
    })
    assert resp.status_code == 422


def test_inbound_conflicting_batch_rejected(db, world):
    """同药同批号再次入库，有效期不一致 —— 拒。"""
    item = NS(drug_id=world["drug"].id, batch_no="B1", production_date=date(2026, 1, 1),
              expiry_date=date(2029, 1, 1), quantity=10, supplier="另一家")
    with pytest.raises(BizError, match="不一致"):
        create_inbound(db, store_id=world["wh"].id, operator="t", items=[item])


def test_inbound_expired_batch_rejected(db, world):
    item = NS(drug_id=world["drug"].id, batch_no="BOLD", production_date=date(2020, 1, 1),
              expiry_date=date(2020, 6, 1), quantity=10, supplier="x")
    with pytest.raises(BizError, match="已过有效期"):
        create_inbound(db, store_id=world["wh"].id, operator="t", items=[item])


# ---------- 调拨留痕 / 拆零台账 ----------

def test_transfer_flow_and_in_transit(db, world):
    """调拨发出即扣、在途可查、收货入帐；重复收货拒。"""
    store, wh, b2 = world["store"], world["wh"], world["b2"]
    t = create_transfer(db, from_store_id=store.id, to_store_id=wh.id,
                        batch_id=b2.id, quantity=15, operator="t")
    assert _stock(db, store.id, b2.id) == 35
    assert t.status == TransferStatus.IN_TRANSIT

    receive_transfer(db, transfer_id=t.id, operator="仓管")
    assert _stock(db, wh.id, b2.id) == 65  # 总仓原 50 + 15
    with pytest.raises(BizError, match="不在在途状态"):
        receive_transfer(db, transfer_id=t.id, operator="仓管")


def test_split_sale_goes_to_split_ledger(db, world):
    """拆零销售：库存照扣、流水类型 SPLIT_SALE、另入拆零台账，不与整盒混。"""
    store, drug, b1 = world["store"], world["drug"], world["b1"]
    create_outbound(db, store_id=store.id, order_type=OrderType.SPLIT_SALE,
                    operator="t", items=[_item(drug.id, 3)])
    assert _stock(db, store.id, b1.id) == 47
    splits = db.query(SplitRecord).all()
    assert len(splits) == 1 and splits[0].quantity == 3
    entry = db.query(StockLedger).filter(StockLedger.change_type == "SPLIT_SALE").one()
    assert entry.qty_change == -3
