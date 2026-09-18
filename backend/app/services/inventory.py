"""库存业务服务：入库、出库 FEFO 扣减、门店调拨、质检停售/放行。

并发不穿账的三道闸：
1. 出库前在同一事务内按 FEFO 选批并汇总可用量，不够直接拒单；
2. 真正扣减用条件更新：UPDATE stock SET qty=qty-:n WHERE id=:id AND qty>=:n，
   影响行数必须为 1，为 0 说明被别的窗口抢先，整单回滚重算；
3. 数据库层 CHECK(qty>=0) 兜底，物理上不允许负数。

SQLite WAL 下，后到的写事务会拿到 SQLITE_BUSY_SNAPSHOT（"database is locked"），
busy_timeout 不会替你解决快照过期——必须整笔事务回滚后重读，所以这里带重试环。
"""
import time
from datetime import date, datetime

from sqlalchemy import and_, delete, exists, func, or_, select, update
from sqlalchemy.exc import IntegrityError, OperationalError

from ..config import BUSY_RETRY
from ..models import (
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
from .expiry import block_reason, is_expired


class BizError(Exception):
    """业务规则拒绝（单据不合法、库存不足、批次被锁等），HTTP 层映射 400。"""


class _Replan(Exception):
    """条件更新落空或快照过期，需回滚后重新选批。"""


def _is_docno_collision(exc: Exception) -> bool:
    # 并发下两事务读到同一日序号，撞单据号唯一约束——回滚重取序号即可
    msg = str(exc)
    return isinstance(exc, IntegrityError) and "UNIQUE constraint failed" in msg and ".no" in msg


def _retry(db, fn, *, what: str):
    """写事务统一重试环：FEFO 重算 / 写锁等待 / 单据号碰撞。"""
    last_err = ""
    for attempt in range(BUSY_RETRY):
        try:
            return fn()
        except _Replan:
            db.rollback()
            last_err = "库存刚发生变动，重新分配批次"
            continue
        except OperationalError as e:
            db.rollback()
            last_err = str(e)
            if "locked" not in str(e).lower() and "busy" not in str(e).lower():
                raise
            time.sleep(min(0.02 * (attempt + 1), 0.3))
            continue
        except IntegrityError as e:
            db.rollback()
            if not _is_docno_collision(e):
                raise
            last_err = "单号碰撞"
            time.sleep(min(0.01 * (attempt + 1), 0.2))
            continue
    raise BizError(f"并发冲突，{what}多次重试仍未完成（{last_err}），请重新提交")


# ---------------------------------------------------------------- 通用工具

def _get(db, model, obj_id, label):
    obj = db.get(model, obj_id)
    if obj is None:
        raise BizError(f"{label}不存在：id={obj_id}")
    return obj


def _next_no(db, model, prefix: str) -> str:
    today = date.today().strftime("%Y%m%d")
    like = f"{prefix}{today}%"
    n = db.scalar(select(func.count()).select_from(model).where(model.no.like(like))) + 1
    return f"{prefix}{today}-{n:03d}"


def _get_or_create_stock(db, batch_id: int, location_id: int) -> Stock:
    stock = db.scalar(
        select(Stock).where(Stock.batch_id == batch_id, Stock.location_id == location_id)
    )
    if stock is None:
        stock = Stock(batch_id=batch_id, location_id=location_id, qty=0)
        db.add(stock)
        db.flush()
    return stock


def _blocked_filter(today: date):
    """批次不可动的 SQL 条件：已过期（当天不算）或质检停售。"""
    return or_(Batch.expiry_date < today, Batch.status == BATCH_HOLD)


def _conditional_consume(db, stock_id: int, need: int, today: date) -> None:
    """条件更新扣减：库存够、且批次此刻未过期未停售，才允许减。"""
    batch_clear = ~exists().where(
        and_(Batch.id == Stock.batch_id, _blocked_filter(today))
    )
    result = db.execute(
        update(Stock)
        .where(Stock.id == stock_id, Stock.qty >= need, batch_clear)
        .values(qty=Stock.qty - need)
    )
    if result.rowcount != 1:
        raise _Replan()


# ---------------------------------------------------------------- 入库

def create_inbound(db, *, drug_id, batch_no, production_date, expiry_date, qty,
                   supplier, operator="仓管员", note=None) -> dict:
    if not batch_no or not supplier:
        raise BizError("批号、供应商不能为空")
    if not isinstance(qty, int) or qty <= 0:
        raise BizError("入库数量必须是最小包装单位的正整数")
    if expiry_date <= production_date:
        raise BizError("有效期至必须晚于生产日期")

    drug = _get(db, Drug, drug_id, "药品")
    warehouse = db.scalar(select(Location).where(Location.kind == "warehouse"))
    if warehouse is None:
        raise BizError("总仓货位缺失")

    def _tx():
        batch = db.scalar(
            select(Batch).where(Batch.drug_id == drug_id, Batch.batch_no == batch_no)
        )
        if batch is None:
            batch = Batch(
                drug_id=drug_id,
                batch_no=batch_no,
                production_date=production_date,
                expiry_date=expiry_date,
                supplier=supplier,
                status=BATCH_NORMAL,
                created_at=date.today(),
            )
            db.add(batch)
            db.flush()
        else:
            # 同药品同批号必须是同一批东西，日期不一致说明录错，不许进账
            if batch.production_date != production_date or batch.expiry_date != expiry_date:
                raise BizError(
                    f"批号 {batch_no} 已存在且生产日期/有效期不一致，"
                    f"台账登记为 {batch.production_date} ~ {batch.expiry_date}，请核实批号"
                )

        stock = _get_or_create_stock(db, batch.id, warehouse.id)
        stock.qty += qty  # 入库只增，CHECK 约束兜底

        no = _next_no(db, Inbound, "RK")
        db.add(Inbound(
            no=no, batch_id=batch.id, drug_id=drug_id, qty=qty, supplier=supplier,
            production_date=production_date, expiry_date=expiry_date,
            operator=operator, created_at=datetime.now(), note=note,
        ))
        db.commit()
        return {"no": no, "batch_id": batch.id, "warehouse_qty": stock.qty}

    return _retry(db, _tx, what="入库")


# ---------------------------------------------------------------- FEFO 选批

def _fefo_plan(db, *, drug_id, location_id, qty, today) -> list[tuple[Stock, Batch, int]]:
    """按 有效期升序（近的在前）、同效期按批号 选批，返回 [(stock, batch, take), ...]。

    过期批、停售批在选批阶段直接剔除——它们摆在货架上也不能动。
    """
    rows = db.execute(
        select(Stock, Batch)
        .join(Batch, Batch.id == Stock.batch_id)
        .where(
            Stock.location_id == location_id,
            Stock.batch_id.in_(select(Batch.id).where(Batch.drug_id == drug_id)),
            Stock.qty > 0,
            ~_blocked_filter(today),
        )
        .order_by(Batch.expiry_date.asc(), Batch.batch_no.asc(), Stock.id.asc())
    ).all()

    plan, remain = [], qty
    for stock, batch in rows:
        if remain <= 0:
            break
        take = min(stock.qty, remain)
        plan.append((stock, batch, take))
        remain -= take

    if remain > 0:
        available = sum(s.qty for s, _ in rows)
        # 给出明确的缺货原因：是不是被锁的批次上有货
        locked = db.execute(
            select(func.coalesce(func.sum(Stock.qty), 0))
            .join(Batch, Batch.id == Stock.batch_id)
            .where(
                Stock.location_id == location_id,
                Batch.drug_id == drug_id,
                _blocked_filter(today),
            )
        ).scalar_one()
        msg = f"可出库库存不足：需要 {qty}，可出 {available}"
        if locked:
            msg += f"；另有 {locked} 在过期/停售批次上，系统锁定不可动用"
        raise BizError(msg)
    return plan


def fefo_preview(db, *, drug_id, location_id, qty) -> dict:
    """出库单提交前给营业员看：系统准备动哪几批。"""
    if not isinstance(qty, int) or qty <= 0:
        raise BizError("出库数量必须是正整数")
    _get(db, Drug, drug_id, "药品")
    _get(db, Location, location_id, "货位")
    today = date.today()
    plan = _fefo_plan(db, drug_id=drug_id, location_id=location_id, qty=qty, today=today)
    return {
        "allocations": [
            {
                "batch_id": b.id, "batch_no": b.batch_no,
                "expiry_date": b.expiry_date.isoformat(),
                "stock_qty": s.qty, "take": take,
            }
            for s, b, take in plan
        ]
    }


# ---------------------------------------------------------------- 出库

def _do_outbound(db, *, drug_id, location_id, qty, kind, operator, note,
                 requested_batch_id, today) -> str:
    drug = _get(db, Drug, drug_id, "药品")
    _get(db, Location, location_id, "货位")

    plan = _fefo_plan(db, drug_id=drug_id, location_id=location_id, qty=qty, today=today)

    # 合规拦截：如果有人指定批次，先查这批本身——锁了就报锁定原因，
    # 没锁但不是 FEFO 第一顺位 = 违反先进先出，系统直接认这个错。
    if requested_batch_id is not None:
        wanted = db.get(Batch, requested_batch_id)
        if wanted is None or wanted.drug_id != drug_id:
            raise BizError("指定的批号不属于该药品或不存在")
        reason = block_reason(wanted, today)
        if reason:
            raise BizError(f"拒绝出库：批号 {wanted.batch_no} {reason}")
        here = db.scalar(
            select(Stock).where(
                Stock.batch_id == requested_batch_id,
                Stock.location_id == location_id,
            )
        )
        if here is None or here.qty <= 0:
            raise BizError(f"批号 {wanted.batch_no} 在本货位无库存，不能指定出库")
        first_batch_id = plan[0][1].id
        if requested_batch_id != first_batch_id:
            first = plan[0][1]
            raise BizError(
                f"拒绝出库：违反近效期先出（FEFO）规则。效期更近的批号 "
                f"{first.batch_no}（有效期至 {first.expiry_date}）尚未出完，"
                f"不允许先动效期更远的批次 {wanted.batch_no}"
            )

    no = _next_no(db, Outbound, "CK" if kind == "sale" else "CL")
    head = Outbound(
        no=no, drug_id=drug_id, location_id=location_id, qty=qty, kind=kind,
        operator=operator, created_at=datetime.now(), note=note,
    )
    db.add(head)
    db.flush()

    for stock, batch, take in plan:
        _conditional_consume(db, stock.id, take, today)
        db.add(OutboundFlow(
            outbound_id=head.id, batch_id=batch.id, location_id=location_id,
            qty=take, expiry_date=batch.expiry_date, created_at=datetime.now(),
        ))
        if kind == "split":
            bulk_size = drug.bulk_size or 1
            db.add(SplitSale(
                outbound_id=head.id, batch_id=batch.id, location_id=location_id,
                qty=take, bulk_packages=take // bulk_size,
                loose_units=take % bulk_size, created_at=datetime.now(),
            ))

    db.commit()
    return no


def create_outbound(db, *, drug_id, location_id, qty, kind="sale",
                    operator="营业员", note=None, requested_batch_id=None) -> dict:
    if kind not in ("sale", "split"):
        raise BizError("出库类型只能是 sale（整包装）/ split（拆零）")

    today = date.today()

    def _tx():
        no = _do_outbound(
            db, drug_id=drug_id, location_id=location_id, qty=qty, kind=kind,
            operator=operator, note=note,
            requested_batch_id=requested_batch_id, today=today,
        )
        return {"no": no}

    return _retry(db, _tx, what="出库")


# ---------------------------------------------------------------- 调拨

def _do_ship(db, *, drug_id, from_location_id, to_location_id, qty, operator, today) -> str:
    if from_location_id == to_location_id:
        raise BizError("调出货位与调入货位不能相同")
    _get(db, Drug, drug_id, "药品")
    _get(db, Location, from_location_id, "调出货位")
    _get(db, Location, to_location_id, "调入货位")

    plan = _fefo_plan(db, drug_id=drug_id, location_id=from_location_id,
                      qty=qty, today=today)

    no = _next_no(db, Transfer, "DB")
    transfer = Transfer(
        no=no, drug_id=drug_id, from_location_id=from_location_id,
        to_location_id=to_location_id, qty=qty, status=TRANSIT,
        operator=operator, shipped_at=datetime.now(),
    )
    db.add(transfer)
    db.flush()
    for stock, batch, take in plan:
        _conditional_consume(db, stock.id, take, today)
        db.add(TransferItem(
            transfer_id=transfer.id, batch_id=batch.id, qty=take,
            expiry_date=batch.expiry_date,
        ))
    db.commit()
    return no


def ship_transfer(db, *, drug_id, from_location_id, to_location_id, qty,
                  operator="仓管员") -> dict:
    if not isinstance(qty, int) or qty <= 0:
        raise BizError("调拨数量必须是正整数")
    today = date.today()

    def _tx():
        no = _do_ship(db, drug_id=drug_id, from_location_id=from_location_id,
                      to_location_id=to_location_id, qty=qty,
                      operator=operator, today=today)
        return {"no": no, "status": TRANSIT}

    return _retry(db, _tx, what="调拨发货")


def receive_transfer(db, *, transfer_id, operator="门店收货员") -> dict:
    transfer = _get(db, Transfer, transfer_id, "调拨单")
    if transfer.status != TRANSIT:
        raise BizError(f"调拨单 {transfer.no} 状态为 {transfer.status}，不能重复收货")

    def _tx():
        # 条件更新抢占：两个窗口同时点收货，只有一单能把 TRANSIT 改成 RECEIVED
        result = db.execute(
            update(Transfer)
            .where(Transfer.id == transfer_id, Transfer.status == TRANSIT)
            .values(status=RECEIVED, received_at=datetime.now())
        )
        if result.rowcount != 1:
            raise _Replan()

        items = db.scalars(
            select(TransferItem).where(TransferItem.transfer_id == transfer_id)
        ).all()
        for item in items:
            # 过期/停售批可以收，但收进来照样锁着不能卖；这里加库存不违规
            stock = _get_or_create_stock(db, item.batch_id, transfer.to_location_id)
            stock.qty += item.qty
        db.commit()
        return {"no": transfer.no, "status": RECEIVED}

    try:
        return _retry(db, _tx, what="调拨收货")
    except BizError:
        # 重试环跑满只可能是状态被并发改走，转成明确的业务提示
        raise BizError(f"调拨单 {transfer.no} 已被其他窗口收货，不能重复入账")


# ---------------------------------------------------------------- 质检

def quality_hold(db, *, batch_id, reason, operator="质检员") -> dict:
    batch = _get(db, Batch, batch_id, "批次")
    if batch.status == BATCH_HOLD:
        raise BizError(f"批号 {batch.batch_no} 已处于停售状态")
    batch.status = BATCH_HOLD
    no = _next_no(db, QualityAction, "ZJ")
    db.add(QualityAction(
        no=no, batch_id=batch_id, action="hold", doc_no=None, reason=reason,
        operator=operator, created_at=datetime.now(),
    ))
    db.commit()
    return {"no": no, "status": BATCH_HOLD}


def quality_release(db, *, batch_id, doc_no, reason=None, operator="质检员") -> dict:
    if not doc_no or not str(doc_no).strip():
        raise BizError("放行必须挂质检放行单编号，口头放行不入账")
    batch = _get(db, Batch, batch_id, "批次")
    if batch.status != BATCH_HOLD:
        raise BizError(f"批号 {batch.batch_no} 当前不是停售状态，无需放行")
    batch.status = BATCH_NORMAL
    no = _next_no(db, QualityAction, "FX")
    db.add(QualityAction(
        no=no, batch_id=batch_id, action="release", doc_no=doc_no.strip(),
        reason=reason, operator=operator, created_at=datetime.now(),
    ))
    db.commit()
    note = ""
    if is_expired(batch):
        note = "注意：该批已超过有效期，放行仅解除停售标记，过期锁定仍然有效，不可出库"
    return {"no": no, "status": BATCH_NORMAL, "note": note}
