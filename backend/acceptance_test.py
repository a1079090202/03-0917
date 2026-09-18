"""交付验收脚本（对着真实 HTTP 服务打，模拟多个浏览器窗口并发）。

跑法：
    cd backend
    python acceptance_test.py

覆盖验收清单：
1. 两个/多个窗口同时出同一批 → 不穿账、无负数、恰如其分扣减；
2. 过期批、停售批出库 → 明确拦截；
3. 指定效期更远的批 → FEFO 违规拦截；自动分配永远近效期优先；
4. 批号召回 → 总入库/总销售/现存/在途/逐店数字与种子纸面账一致，平衡为 0；
5. 上月/本月报表能出账，近效期/过期/停售清单与批次流向齐全；
6. 入库缺要素 422、同批号日期打架 400、放行无单号 400、重复收货 400、拆零独立账。
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
PORT = 8123
BASE = f"http://127.0.0.1:{PORT}"

PASS, FAIL = "✅ PASS", "❌ FAIL"
results = []


def check(name, ok, detail=""):
    results.append((name, ok, detail))
    print(f"{PASS if ok else FAIL}  {name}" + (f"  —— {detail}" if detail and not ok else ""))


def req(method, path, body=None, timeout=30):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(
        BASE + path, data=data, method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}


def wait_up(proc, seconds=40):
    deadline = time.time() + seconds
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError("uvicorn 提前退出")
        try:
            status, _ = req("GET", "/api/health", timeout=2)
            if status == 200:
                return
        except Exception:
            time.sleep(0.3)
    raise RuntimeError("服务启动超时")


def main():
    tmp = Path(tempfile.mkdtemp(prefix="pharma_accept_"))
    os.environ["PHARMA_DATA_DIR"] = str(tmp)
    os.environ["PHARMA_DB"] = str(tmp / "pharma.db")
    sys.path.insert(0, str(BACKEND_DIR))

    print(f"临时数据库：{tmp}")
    from app.seed import build
    build()

    env = os.environ.copy()
    extra = str(BACKEND_DIR / ".pydeps")
    if (BACKEND_DIR / ".pydeps").exists():
        env["PYTHONPATH"] = extra + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app",
         "--host", "127.0.0.1", "--port", str(PORT), "--log-level", "warning"],
        cwd=BACKEND_DIR, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )

    try:
        wait_up(proc)
        drugs = req("GET", "/api/drugs")[1]
        locs = req("GET", "/api/locations")[1]
        wh = next(l["id"] for l in locs if l["kind"] == "warehouse")
        store = {l["name"]: l["id"] for l in locs if l["kind"] == "store"}
        drug = {d["code"]: d["id"] for d in drugs}
        batches = req("GET", "/api/batches")[1]
        bno = {b["batch_no"]: b for b in batches}

        # ------------------------------------------------ 1. 并发不穿账
        # 效期设 150 天后，确保它是总仓该药 FEFO 第一顺位（近效期但可售），
        # 12 个窗口抢的就是这 100 支本身
        import datetime
        _today = datetime.date.today()
        rc_expiry = (_today + datetime.timedelta(days=150)).isoformat()
        status, inb = req("POST", "/api/inbound", {
            "drug_id": drug["YP013"], "batch_no": "RCTEST-CONC",
            "production_date": "2024-09-01", "expiry_date": rc_expiry,
            "qty": 100, "supplier": "验收测试供应商",
        })
        check("验收批入库 100", status == 200)
        rc_batch_id = inb["batch_id"]

        # 计算该药品在总仓的全部可出库存（排除过期/停售批）
        yb = req("GET", f"/api/batches?drug_id={drug['YP013']}")[1]
        available = sum(
            next((d["qty"] for d in b["distribution"] if d["location_id"] == wh), 0)
            for b in yb if b["flag"] in ("normal", "near")
        )
        check("该药品总仓可出库存统计为正", available >= 100, f"available={available}")

        outcomes, lock = [], threading.Lock()

        def fire():
            # 每个窗口都要把全部可出库存一次提走——模拟多人抢最后一批
            s, d = req("POST", "/api/outbound", {
                "drug_id": drug["YP013"], "location_id": wh,
                "qty": available, "kind": "sale", "operator": "并发窗口",
            })
            with lock:
                outcomes.append((s, d))

        with ThreadPoolExecutor(max_workers=12) as pool:
            list(pool.map(lambda _: fire(), range(12)))

        ok_n = sum(1 for s, _ in outcomes if s == 200)
        bad = [d for s, d in outcomes if s not in (200, 400)]
        check("12 个窗口各抢全部库存：恰好 1 单成功", ok_n == 1, f"实际成功 {ok_n} 单")
        check("其余 11 单全部被业务层 400 拒绝（无 500）",
              sum(1 for s, _ in outcomes if s == 400) == 11 and not bad, str(bad[:1]))

        left = req("GET", f"/api/batches?drug_id={drug['YP013']}")[1]
        remain = sum(
            next((d["qty"] for d in b["distribution"] if d["location_id"] == wh), 0)
            for b in left if b["flag"] in ("normal", "near")
        )
        check("抢完后可出库存为 0，没有卖穿", remain == 0, f"剩余 {remain}")
        rc_qty = next((b["total_qty"] for b in left if b["batch_no"] == "RCTEST-CONC"), 0)
        check("验收批本身清零", rc_qty == 0, f"剩余 {rc_qty}")

        # 该批清零后，两个窗口还指定它抢：必须双双拒绝（不能穿成负数）
        rc = {"id": rc_batch_id}
        with ThreadPoolExecutor(max_workers=2) as pool:
            zero = list(pool.map(lambda _: req("POST", "/api/outbound", {
                "drug_id": drug["YP013"], "location_id": wh, "qty": 10,
                "kind": "sale", "requested_batch_id": rc["id"]})[0], range(2)))
        check("清零批双窗口再抢全部拦截", sorted(zero) == [400, 400], str(zero))

        # ------------------------------------------------ 2. 过期批拦截
        exp_batch = req("GET", "/api/batches?flag=expired")[1][0]
        s, d = req("POST", "/api/outbound", {
            "drug_id": exp_batch["drug_id"], "location_id": wh,
            "qty": 1, "requested_batch_id": exp_batch["id"]})
        check("指定过期批出库被锁死拦截",
              s == 400 and "到期" in d.get("detail", ""), d.get("detail"))

        s, prev = req("POST", "/api/outbound/preview", {
            "drug_id": exp_batch["drug_id"], "location_id": wh, "qty": 1})
        alloc_safe = all(a["batch_no"] != exp_batch["batch_no"] for a in prev["allocations"])
        check("自动 FEFO 永远不会分配到过期批", s == 200 and alloc_safe)

        # ------------------------------------------------ 3. 停售批拦截 + 放行流程
        hold_batch = req("GET", "/api/batches?flag=hold")[1][0]
        s, d = req("POST", "/api/outbound", {
            "drug_id": hold_batch["drug_id"], "location_id": wh,
            "qty": 1, "requested_batch_id": hold_batch["id"]})
        check("指定质检停售批出库被拦截",
              s == 400 and "停售" in d.get("detail", ""), d.get("detail"))

        s, prev = req("POST", "/api/outbound/preview", {
            "drug_id": hold_batch["drug_id"], "location_id": wh, "qty": 1})
        check("自动 FEFO 跳过停售批",
              all(a["batch_no"] != hold_batch["batch_no"] for a in prev["allocations"]))

        s, d = req("POST", "/api/quality/release", {
            "batch_id": hold_batch["id"], "doc_no": "  "})
        check("空白放行单编号被拒（口头放行不算）", s == 400)

        # 停售一个新批做放→验闭环
        req("POST", "/api/inbound", {
            "drug_id": drug["YP014"], "batch_no": "QATEST-REL",
            "production_date": "2025-06-01", "expiry_date": "2027-06-01",
            "qty": 50, "supplier": "验收测试供应商"})
        qb = next(b for b in req("GET", f"/api/batches?drug_id={drug['YP014']}")[1]
                  if b["batch_no"] == "QATEST-REL")
        check("停售新批", req("POST", "/api/quality/hold",
              {"batch_id": qb["id"], "reason": "验收停售"})[0] == 200)
        s, d = req("POST", "/api/outbound", {
            "drug_id": drug["YP014"], "location_id": wh,
            "qty": 1, "requested_batch_id": qb["id"]})
        check("停售后该批即不可出", s == 400)
        s, d = req("POST", "/api/quality/release", {
            "batch_id": qb["id"], "doc_no": "FXD-2026-0001"})
        check("挂质检放行单后恢复", s == 200, d)

        # ------------------------------------------------ 4. FEFO 违规
        hg = bno["HG20260418"]
        same_drug_batches = [b for b in req(
            "GET", f"/api/batches?drug_id={hg['drug_id']}")[1] if b["total_qty"] > 0]
        far = [b for b in same_drug_batches if b["id"] != hg["id"]]
        s, d = req("POST", "/api/outbound", {
            "drug_id": hg["drug_id"], "location_id": wh,
            "qty": 1, "requested_batch_id": far[0]["id"]})
        check("故意先出效期远的批被判违规",
              s == 400 and "FEFO" in d.get("detail", "") and hg["batch_no"] in d.get("detail", ""),
              d.get("detail"))
        s, prev = req("POST", "/api/outbound/preview", {
            "drug_id": hg["drug_id"], "location_id": wh, "qty": 5})
        check("自动 FEFO 第一顺位是近效期召回批",
              prev["allocations"][0]["batch_no"] == "HG20260418")

        # ------------------------------------------------ 5. 召回追溯（纸面对账）
        s, tr = req("GET", "/api/recalls/trace?batch_no=HG20260418")
        check("召回查询成功", s == 200)
        check("召回平衡式 = 0（进600 = 销115 + 存425 + 在途60）",
              tr["summary"] == {
                  "total_received": 600, "total_sold": 115,
                  "total_current": 425, "total_in_transit": 60,
                  "balance_check": 0},
              str(tr["summary"]))
        expect = {"总仓": (600, 0, 360, 240), "中山一路店": (120, 65, 0, 55),
                  "人民广场店": (100, 30, 0, 70), "解放桥店": (80, 20, 0, 60)}
        ok = True
        detail = []
        for l in tr["locations"]:
            if l["location_name"] in expect:
                tup = (l["received_qty"], l["sold_qty"],
                       l["shipped_out_qty"], l["current_qty"])
                if tup != expect[l["location_name"]]:
                    ok, detail_msg = False, f"{l['location_name']}={tup}"
        check("召回逐店数字与纸面流向一致（收/销/调/存）", ok, str(detail))
        transit_ok = any(t["to"] == "滨江大道店" and t["qty"] == 60
                         for t in tr["in_transit"])
        check("在途 60 支压在 总仓→滨江大道店 单上", transit_ok, str(tr["in_transit"]))
        check("8 家门店 + 总仓全部列出（不漏店）", len(tr["locations"]) == 9)

        # ------------------------------------------------ 6. 拆零独立账
        s, d = req("POST", "/api/outbound", {
            "drug_id": hg["drug_id"], "location_id": store["中山一路店"],
            "qty": 15, "kind": "split", "operator": "拆零验收"})
        check("拆零出库 15 支成功", s == 200, d)
        sp = req("GET", "/api/ledger/splits?limit=5")[1][0]
        check("拆零台账：15 支 = 1 盒 + 5 支零头，独立记账",
              sp["qty"] == 15 and sp["bulk_packages"] == 1 and sp["loose_units"] == 5,
              str(sp))

        # ------------------------------------------------ 7. 调拨与重复收货
        transfers = req("GET", "/api/ledger/transfers?limit=200")[1]
        t_in = next(t for t in transfers if t["status"] == "in_transit")
        s1, _ = req("POST", f"/api/transfers/{t_in['id']}/receive", {})
        s2, d2 = req("POST", f"/api/transfers/{t_in['id']}/receive", {})
        check("在途单首次收货成功", s1 == 200)
        check("同一在途单重复收货被拦截（不会重复入账）", s2 == 400, d2.get("detail"))

        # ------------------------------------------------ 8. 入库要素
        s, _ = req("POST", "/api/inbound", {
            "drug_id": drug["YP001"], "batch_no": "X",
            "production_date": "2026-01-01", "expiry_date": "2027-01-01",
            "qty": 10})  # 缺供应商
        check("入库缺供应商 → 422 进不了账", s == 422)
        s, d = req("POST", "/api/inbound", {
            "drug_id": hg["drug_id"], "batch_no": "HG20260418",
            "production_date": "2020-01-01", "expiry_date": "2030-01-01",
            "qty": 1, "supplier": "乱填供应商"})
        check("同批号生产日期/有效期与台账打架 → 400", s == 400, d.get("detail"))

        # ------------------------------------------------ 9. 月度报表
        import datetime
        today = datetime.date.today()
        rep = req("GET", f"/api/reports/monthly?year={today.year}&month={today.month}")[1]
        near_nos = {r["batch_no"] for r in rep["near_expiry"]}
        check("本月近效期清单含 2 个预警批",
              {"A00320250301", "A00720250701"} <= near_nos, str(near_nos))
        check("本月过期清单含前年注射液",
              any(r["batch_no"] == "20220108A" for r in rep["expired"]))
        check("本月停售清单列出质检批",
              any(r["batch_no"] == hold_batch["batch_no"] for r in rep["quality_hold"]))
        # 验收过程中新建了 RCTEST-CONC / QATEST-REL 两个批，故应为 32 行
        check("批次流向表含全部 30 个种子批", len(rep["batch_flows"]) >= 30,
              f"{len(rep['batch_flows'])} 行")
        # 默认（不带年月）= 上月，也必须能出账
        s, lastm = req("GET", "/api/reports/monthly")
        check("默认月报（上月）可出账", s == 200 and "batch_flows" in lastm)

        # ------------------------------------------------ 10. 物理无负数
        import sqlite3
        dbp = os.environ["PHARMA_DB"]
        neg = sqlite3.connect(dbp).execute(
            "SELECT COUNT(*) FROM stock WHERE qty < 0").fetchone()[0]
        check("数据库物理层无负库存（CHECK 兜底）", neg == 0, f"负数行 {neg}")

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()

    failed = [r for r in results if not r[1]]
    print("\n" + "=" * 64)
    print(f"验收结果：{len(results) - len(failed)}/{len(results)} 通过")
    if failed:
        for n, _, d in failed:
            print(f"  未通过：{n}  {d}")
        sys.exit(1)
    print("全部验收项通过，可以按业务清单人工复验。")


if __name__ == "__main__":
    main()
