"""演示数据播种（可重复执行，先清库再播种）。

固定内容：
- 15 个药品、总仓 + 8 家门店；
- 30 个批次：1 批已过期（前年就该销毁的注射液）、
  2 批落在 6 个月近效期窗口、1 批质检停售；
- 近三个月（相对今天）入库/调拨/销售/拆零流水，
  其中召回样板批号 HG20260418 发往 3 家门店、有销售、另有 60 支在途；
- 含 1 笔门店→门店调拨、2 笔在途调拨。

用法：
    python -m app.seed            # 仅当库不存在时建库播种
    python -m app.seed --force    # 清掉重建（重置演示数据）
"""
import argparse
import random
from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select

from .database import engine, SessionLocal
from .models import (
    Base,
    Batch,
    BATCH_HOLD,
    BATCH_NORMAL,
    Drug,
    Inbound,
    Location,
    Outbound,
    OutboundFlow,
    QualityAction,
    SplitSale,
    Stock,
    Transfer,
    TRANSIT,
    RECEIVED,
    TransferItem,
)

rng = random.Random(20260918)
TODAY = date.today()


def _dt(days_ago: int, h: int = 10, m: int | None = None) -> datetime:
    return datetime.combine(
        TODAY - timedelta(days=days_ago),
        time(h, m if m is not None else (days_ago * 7) % 60),
    )


def shift_months(d: date, months: int) -> date:
    m = d.month - 1 + months
    year = d.year + m // 12
    month = m % 12 + 1
    day = min(d.day, 28)
    return date(year, month, day)


# ------------------------------------------------------------ 基础档案

DRUGS = [
    # code, 名称, 规格, 厂家, 最小单位, 大包装单位, 包装量
    ("YP001", "氯化钠注射液", "100ml:0.9g 玻璃瓶", "华润双鹤药业", "瓶", None, None),
    ("YP002", "葡萄糖酸钙注射液", "10ml:1g", "河北天成药业", "支", "盒", 10),
    ("YP003", "阿莫西林胶囊", "0.25g*24粒", "珠海联邦制药", "粒", "盒", 24),
    ("YP004", "布洛芬缓释胶囊", "0.3g*20粒", "中美史克", "粒", "盒", 20),
    ("YP005", "头孢克肟分散片", "0.1g*12片", "广药白云山", "片", "盒", 12),
    ("YP006", "蒙脱石散", "3g*15袋", "博福-益普生", "袋", "盒", 15),
    ("YP007", "复方丹参滴丸", "27mg*180丸", "天士力制药", "丸", "盒", 180),
    ("YP008", "硝苯地平控释片", "30mg*7片", "拜耳医药", "片", "盒", 7),
    ("YP009", "盐酸二甲双胍片", "0.5g*20片", "中美上海施贵宝", "片", "盒", 20),
    ("YP010", "维生素C片", "0.1g*100片", "华北制药", "片", "瓶", 100),
    ("YP011", "藿香正气水", "10ml*10支", "太极集团", "支", "盒", 10),
    ("YP012", "氯雷他定片", "10mg*6片", "扬子江药业", "片", "盒", 6),
    ("YP013", "奥美拉唑肠溶胶囊", "20mg*14粒", "阿斯利康", "粒", "盒", 14),
    ("YP014", "甲硝唑片", "0.2g*21片", "远大医药", "片", "盒", 21),
    ("YP015", "开塞露(含甘油)", "20ml*20支", "福元药业", "支", "盒", 20),
]

STORE_NAMES = ["中山一路店", "人民广场店", "解放桥店", "滨江大道店",
               "学府路店", "城东新区店", "经开区店", "南站枢纽店"]

SUPPLIERS = ["国控医药有限公司", "华润医药商业", "九州通医药集团",
             "上药控股有限公司", "本地民生医药批发部"]


def build():
    print("重建数据库...")
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    db = SessionLocal()

    try:
        # ---------------- 货位 ----------------
        wh = Location(code="WH", name="总仓", kind="warehouse")
        db.add(wh)
        stores = [Location(code=f"S{i:02d}", name=STORE_NAMES[i - 1], kind="store")
                  for i in range(1, 9)]
        db.add_all(stores)
        db.flush()
        locs = [wh] + stores

        # ---------------- 药品与批次 ----------------
        drug_objs, batch_objs = [], {}
        # key=(drug_code, 'A'/'B') -> Batch
        for idx, (code, name, spec, maker, unit, bulk_unit, bulk_size) in enumerate(DRUGS):
            d = Drug(code=code, name=name, spec=spec, manufacturer=maker,
                     unit=unit, bulk_unit=bulk_unit, bulk_size=bulk_size)
            db.add(d)
            db.flush()
            drug_objs.append(d)

            # 默认效期：A 批 9~14 个月后，B 批 17~28 个月后
            a_exp = shift_months(TODAY, 9 + idx % 6)
            b_exp = shift_months(TODAY, 17 + idx % 8)
            a_prod = shift_months(a_exp, -24)
            b_prod = shift_months(b_exp, -24)
            a_no = f"{code.replace('YP', 'A')}2025{idx + 1:02d}01"
            b_no = f"{code.replace('YP', 'B')}2026{idx + 1:02d}01"

            a_in = 300 + idx * 23
            b_in = 240 + idx * 17

            # ---- 特批：1 过期、2 近效期、1 停售、1 召回样板 ----
            if code == "YP001":
                # 前年就该销毁还压在货架上的注射液
                a_exp = shift_months(TODAY, -25)
                a_prod = shift_months(a_exp, -24)
                a_no = "20220108A"
                a_in = 30
            elif code == "YP002":
                a_exp = shift_months(TODAY, 10)
                a_no = "HG20260418"   # 召回追溯样板批（效期比 B 批近，FEFO 先发它）
                a_in = 600
                b_in = 300
            elif code == "YP003":
                a_exp = shift_months(TODAY, 2)   # 近效期①
                a_prod = shift_months(a_exp, -24)
            elif code == "YP007":
                a_exp = shift_months(TODAY, 4)   # 近效期②
                a_prod = shift_months(a_exp, -24)
            elif code == "YP005":
                a_exp = shift_months(TODAY, 18)  # 质检停售批（日期正常）

            ba = Batch(drug_id=d.id, batch_no=a_no, production_date=a_prod,
                       expiry_date=a_exp, supplier=SUPPLIERS[idx % len(SUPPLIERS)],
                       status=BATCH_NORMAL, created_at=a_prod)
            bb = Batch(drug_id=d.id, batch_no=b_no, production_date=b_prod,
                       expiry_date=b_exp, supplier=SUPPLIERS[(idx + 2) % len(SUPPLIERS)],
                       status=BATCH_NORMAL, created_at=b_prod)
            db.add_all([ba, bb])
            db.flush()
            batch_objs[(code, "A")] = (ba, a_in)
            batch_objs[(code, "B")] = (bb, b_in)

        db.commit()

        # ---------------- 流水模拟器（FEFO + 锁批跳过）----------------
        stock: dict[tuple[int, int], int] = {}
        seq = {"RK": 0, "DB": 0, "CK": 0, "CL": 0, "ZJ": 0}

        # YP005-A 在第 20 天被判停售：这一天之后的任何流水都不许再动它
        hold_ts = _dt(20)
        hold_batch_id = batch_objs[("YP005", "A")][0].id

        def next_no(prefix, ts):
            seq[prefix] += 1
            return f"{prefix}{ts.strftime('%Y%m%d')}-{seq[prefix]:03d}"

        def add_inbound(code, kind_key, qty, ts):
            b, _ = batch_objs[(code, kind_key)]
            d = next(d for d in drug_objs if d.code == code)
            stock[(b.id, wh.id)] = stock.get((b.id, wh.id), 0) + qty
            db.add(Inbound(
                no=next_no("RK", ts), batch_id=b.id, drug_id=d.id, qty=qty,
                supplier=b.supplier, production_date=b.production_date,
                expiry_date=b.expiry_date, operator="仓管员",
                created_at=ts, note="采购入库",
            ))

        def fefo_take(drug_id, loc_id, need, ts):
            """按 FEFO 从某货位真实可用批次分配，返回 [(batch, take)]。"""
            cands = []
            for (bid, lid), q in stock.items():
                if lid != loc_id or q <= 0:
                    continue
                b = db.get(Batch, bid)
                if b.drug_id != drug_id:
                    continue
                if b.expiry_date < TODAY or b.status == BATCH_HOLD:
                    continue  # 过期/停售：种子流水里也不许动
                if bid == hold_batch_id and ts >= hold_ts:
                    continue  # 该批第 20 天起停售，之后的流水不得再动
                cands.append((b.expiry_date, b.batch_no, b.id, q))
            cands.sort()
            plan, remain = [], need
            for _, _, bid, q in cands:
                take = min(q, remain)
                if take:
                    plan.append((bid, take))
                    remain -= take
                if remain == 0:
                    break
            return plan if remain == 0 else None

        def ship(code, from_idx, to_idx, qty, ts, in_transit=False, recv_days=2):
            d = next(x for x in drug_objs if x.code == code)
            plan = fefo_take(d.id, locs[from_idx].id, qty, ts)
            if plan is None:
                return False
            t = Transfer(
                no=next_no("DB", ts), drug_id=d.id,
                from_location_id=locs[from_idx].id, to_location_id=locs[to_idx].id,
                qty=qty, status=TRANSIT if in_transit else RECEIVED,
                operator="仓管员", shipped_at=ts,
                received_at=None if in_transit else _dt(
                    max(0, (TODAY - ts.date()).days - recv_days), ts.hour),
            )
            db.add(t)
            db.flush()
            for bid, take in plan:
                b = db.get(Batch, bid)
                stock[(bid, locs[from_idx].id)] -= take
                db.add(TransferItem(transfer_id=t.id, batch_id=bid, qty=take,
                                    expiry_date=b.expiry_date))
                if not in_transit:
                    stock[(bid, locs[to_idx].id)] = \
                        stock.get((bid, locs[to_idx].id), 0) + take
            return True

        def sell(code, loc_idx, qty, ts, split=False):
            d = next(x for x in drug_objs if x.code == code)
            kind = "split" if split else "sale"
            plan = fefo_take(d.id, locs[loc_idx].id, qty, ts)
            if plan is None:
                return False
            head = Outbound(
                no=next_no("CL" if split else "CK", ts), drug_id=d.id,
                location_id=locs[loc_idx].id, qty=qty, kind=kind,
                operator=f"{STORE_NAMES[loc_idx - 1][:2]}营业员",
                created_at=ts, note="拆零销售" if split else "门店销售",
            )
            db.add(head)
            db.flush()
            for bid, take in plan:
                b = db.get(Batch, bid)
                stock[(bid, locs[loc_idx].id)] -= take
                db.add(OutboundFlow(
                    outbound_id=head.id, batch_id=bid,
                    location_id=locs[loc_idx].id, qty=take,
                    expiry_date=b.expiry_date, created_at=ts,
                ))
                if split:
                    bs = d.bulk_size or 1
                    db.add(SplitSale(
                        outbound_id=head.id, batch_id=bid,
                        location_id=locs[loc_idx].id, qty=take,
                        bulk_packages=take // bs, loose_units=take % bs,
                        created_at=ts,
                    ))
            return True

        # ---------------- 入库 ----------------
        for idx, (code, *_rest) in enumerate(DRUGS):
            ba, a_in = batch_objs[(code, "A")]
            bb, b_in = batch_objs[(code, "B")]
            if code == "YP001":
                add_inbound(code, "A", a_in, _dt(900, 9))      # 过期注射液老入库
            elif code in ("YP003", "YP007"):
                add_inbound(code, "A", a_in, _dt(200, 9))      # 近效期批较早入库
            elif code == "YP005":
                add_inbound(code, "A", a_in, _dt(120, 9))      # 停售批
            else:
                add_inbound(code, "A", a_in, _dt(72 + idx % 18, 9))
            add_inbound(code, "B", b_in, _dt(18 + idx % 20, 11))

        # ---------------- 召回样板批 HG20260418（YP002-A）----------------
        # 发 S01/S02/S03 已收货并有销售，另有 60 支在途压往 S04
        ship("YP002", 0, 1, 120, _dt(70))
        ship("YP002", 0, 2, 100, _dt(55))
        ship("YP002", 0, 3, 80, _dt(40))
        sell("YP002", 1, 40, _dt(58))
        sell("YP002", 1, 25, _dt(22), split=True)
        sell("YP002", 2, 30, _dt(40))
        sell("YP002", 3, 20, _dt(18), split=True)
        ship("YP002", 0, 4, 60, _dt(2), in_transit=True)  # 在途

        # ---------------- 近效期批的流向 ----------------
        ship("YP003", 0, 2, 60, _dt(60))
        ship("YP003", 0, 6, 60, _dt(35))
        sell("YP003", 2, 20, _dt(42))
        sell("YP003", 6, 10, _dt(12))
        ship("YP007", 0, 7, 40, _dt(50))
        sell("YP007", 7, 12, _dt(20))

        # ---------------- 每个药：调拨覆盖 8 家门店 + 常规销售 ----------------
        for idx, (code, *_rest) in enumerate(DRUGS):
            if code in ("YP002",):
                continue  # 上面手工铺过
            # 强制 8 家门店在三个月里都收过货
            forced_store = (idx % 8) + 1
            ship(code, 0, forced_store, 40 + idx % 5 * 10, _dt(66 - idx % 30))
            # 额外 1~2 笔调拨
            for _ in range(1 + idx % 2):
                to = rng.randint(1, 8)
                qty = rng.choice([30, 40, 50, 60, 80, 100])
                if ship(code, 0, to, qty, _dt(rng.randint(8, 64))):
                    # 门店收货后产生 1~2 笔销售（含拆零）
                    d = next(x for x in drug_objs if x.code == code)
                    for k in range(1 + rng.randint(0, 1)):
                        sold = max(1, int(qty * rng.choice([0.2, 0.3, 0.5])))
                        split_ok = d.bulk_size is not None and rng.random() < 0.4
                        sell(code, to, sold, _dt(rng.randint(2, 40)), split=split_ok)
                        qty -= sold

        # ---------------- 门店→门店调拨 1 笔 ----------------
        ship("YP004", 1, 5, 20, _dt(9))

        # ---------------- 另有一笔在途（YP010 总仓→S08）----------------
        ship("YP010", 0, 8, 30, _dt(3), in_transit=True)

        db.commit()

        # ---------------- 质检停售 ----------------
        hold_batch, _ = batch_objs[("YP005", "A")]
        hold_batch.status = BATCH_HOLD
        db.add(QualityAction(
            no=next_no("ZJ", _dt(20)), batch_id=hold_batch.id, action="hold",
            doc_no=None, reason="抽检溶出度不合格，暂停销售待处理",
            operator="质检员", created_at=_dt(20),
        ))
        db.commit()

        # ---------------- 落最终库存 ----------------
        for (bid, lid), q in stock.items():
            if q > 0:
                db.add(Stock(batch_id=bid, location_id=lid, qty=q))
        db.commit()

        # ---------------- 自检：每批 进=销+存+在途 ----------------
        problems = []
        for code, *_ in DRUGS:
            for k in ("A", "B"):
                b, _ = batch_objs[(code, k)]
                inbound = db.scalar(
                    select(func.coalesce(func.sum(Inbound.qty), 0))
                    .where(Inbound.batch_id == b.id))
                sold = db.scalar(
                    select(func.coalesce(func.sum(OutboundFlow.qty), 0))
                    .where(OutboundFlow.batch_id == b.id))
                onhand = db.scalar(
                    select(func.coalesce(func.sum(Stock.qty), 0))
                    .where(Stock.batch_id == b.id))
                transit = db.scalar(
                    select(func.coalesce(func.sum(TransferItem.qty), 0))
                    .join(Transfer, Transfer.id == TransferItem.transfer_id)
                    .where(TransferItem.batch_id == b.id,
                           Transfer.status == TRANSIT))
                if inbound != sold + onhand + transit:
                    problems.append(
                        f"{code}-{k} 进{inbound} 销{sold} 存{onhand} 在途{transit}")
        if problems:
            raise RuntimeError("种子数据对不平：" + "；".join(problems))

        print(f"完成：{len(DRUGS)} 个药品、{len(batch_objs)} 个批次、"
              f"{len(locs)} 个货位，账实平衡校验通过。")
        print("召回验收请用批号 HG20260418；过期批 20220108A；停售批见质检台账。")
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="清库重建")
    args = parser.parse_args()

    from .config import DB_PATH
    if DB_PATH.exists() and not args.force:
        print(f"数据库已存在（{DB_PATH}），跳过播种。重置请用 --force。")
        return
    build()


if __name__ == "__main__":
    main()
