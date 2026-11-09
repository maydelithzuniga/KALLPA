"""Indicadores del negocio calculados con reglas propias (sin IA).

Todo sale de los movimientos confirmados y sus líneas de caja/stock.
"""
from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import ledger
from . import models as M
from . import units
from .money import soles
from .textutil import pluralize, weekday_plural
from .timeutil import DIAS, add_months, day_bounds, month_start, now_lima, today_lima

OUT_KINDS = {M.PURCHASE, M.EXPENSE, M.WITHDRAWAL, M.DEBT_PAYMENT}


def movements(db: Session, business_id: int, start: datetime | None = None, end: datetime | None = None,
              kinds: set[str] | None = None) -> list[M.Movement]:
    q = select(M.Movement).where(M.Movement.business_id == business_id, M.Movement.status == "confirmado")
    if start:
        q = q.where(M.Movement.occurred_at >= start)
    if end:
        q = q.where(M.Movement.occurred_at < end)
    if kinds:
        q = q.where(M.Movement.kind.in_(kinds))
    return list(db.scalars(q.order_by(M.Movement.occurred_at)).all())


def _bounds(start: date, end_exclusive: date) -> tuple[datetime, datetime]:
    return datetime(start.year, start.month, start.day), datetime(end_exclusive.year, end_exclusive.month, end_exclusive.day)


# ------------------------------------------------------------------ periodo

def period_stats(db: Session, business: M.Business, start: date, end_exclusive: date) -> dict[str, Any]:
    s, e = _bounds(start, end_exclusive)
    mvs = movements(db, business.id, s, e)
    st: dict[str, Any] = {
        "start": start.isoformat(), "end": (end_exclusive - timedelta(days=1)).isoformat(),
        "sales_cents": 0, "sales_count": 0, "units_sold": 0,
        "collected_by_method": {"efectivo": 0, "yape": 0},
        "sales_by_method": {"efectivo": 0, "yape": 0, "fiado": 0},
        "collections_cents": 0, "discounts_cents": 0, "discount_sales": 0,
        "purchases_cents": 0, "expenses_cents": 0, "fixed_expenses_cents": 0, "variable_expenses_cents": 0,
        "withdrawals_cents": 0, "contributions_cents": 0, "debt_payments_cents": 0, "transfers_cents": 0,
        "savings_cents": 0, "new_credit_cents": 0, "cogs_cents": 0, "sales_without_cost": 0,
        "inflow_cents": 0, "outflow_cents": 0, "active_days": 0, "goal_savings_cents": 0,
        "expenses_by_category": defaultdict(int), "non_inventory_purchases_cents": 0, "loss_cents": 0, "loss_profit_cents": 0,
    }
    days = set()
    for mv in mvs:
        days.add(mv.occurred_at.date())
        k = mv.kind
        if k == M.SALE:
            st["sales_cents"] += mv.amount_cents
            st["sales_count"] += 1
            st["units_sold"] += mv.quantity or 0
            if mv.paid_cents and mv.method in M.POCKETS:
                st["collected_by_method"][mv.method] += mv.paid_cents
                st["sales_by_method"][mv.method] += mv.paid_cents
            credit = mv.amount_cents - mv.paid_cents
            if credit > 0:
                st["sales_by_method"]["fiado"] += credit
                st["new_credit_cents"] += credit
            if mv.discount_cents:
                st["discounts_cents"] += mv.discount_cents
                st["discount_sales"] += 1
            if mv.product and mv.product.is_service:
                pass
            elif mv.unit_cost_cents is not None and mv.product and mv.product.track_stock and units.base_qty(mv):
                # solo inventario controlado: lo no controlado (insumos sin stock) ya se cuenta al comprar
                st["cogs_cents"] += round(mv.unit_cost_cents * units.base_qty(mv))
            elif mv.product_id and mv.product and mv.product.track_stock:
                st["sales_without_cost"] += 1
        elif k == M.LOSS:
            st["loss_cents"] += mv.amount_cents
            # baja la ganancia si es plata, otra cosa, o mercadería con stock controlado
            # (la mercadería sin stock controlado ya se contó como gasto al comprarla)
            if mv.expense_type in ("plata", "otro") or (mv.product and mv.product.track_stock):
                st["loss_profit_cents"] += mv.amount_cents
        elif k == M.COLLECTION:
            st["collections_cents"] += mv.amount_cents
            st["collected_by_method"][mv.method] += mv.amount_cents
        elif k == M.PURCHASE:
            st["purchases_cents"] += mv.paid_cents
            tracked = mv.product is not None and mv.product.track_stock and (mv.quantity or mv.measure)
            if not tracked:
                st["non_inventory_purchases_cents"] += mv.amount_cents
        elif k == M.EXPENSE:
            st["expenses_cents"] += mv.amount_cents
            st["expenses_by_category"][mv.category or "Otros"] += mv.amount_cents
            if mv.expense_type == "fijo":
                st["fixed_expenses_cents"] += mv.amount_cents
            else:
                st["variable_expenses_cents"] += mv.amount_cents
        elif k == M.WITHDRAWAL:
            st["withdrawals_cents"] += mv.amount_cents
        elif k == M.CONTRIBUTION:
            st["contributions_cents"] += mv.amount_cents
        elif k == M.DEBT_PAYMENT:
            st["debt_payments_cents"] += mv.amount_cents
        elif k == M.TRANSFER:
            st["transfers_cents"] += mv.amount_cents
        elif k == M.GOAL_SAVING:
            st["goal_savings_cents"] += mv.amount_cents
    st["active_days"] = len(days)
    st["collected_cents"] = sum(st["collected_by_method"].values())
    # Flujo de caja del negocio: lo que entró por ventas/cobros menos lo que salió por compras, gastos y cuotas
    st["business_inflow_cents"] = st["collected_cents"]
    st["business_outflow_cents"] = st["purchases_cents"] + st["expenses_cents"] + st["debt_payments_cents"]
    st["business_cashflow_cents"] = st["business_inflow_cents"] - st["business_outflow_cents"]
    # Flujo total incluye la casa (retiros) y aportes propios
    st["inflow_cents"] = st["business_inflow_cents"] + st["contributions_cents"]
    st["outflow_cents"] = st["business_outflow_cents"] + st["withdrawals_cents"]
    st["net_cashflow_cents"] = st["inflow_cents"] - st["outflow_cents"]
    # Ganancia: ventas − costo de lo vendido − gastos del negocio − compras que no son inventario
    st["gross_profit_cents"] = st["sales_cents"] - st["cogs_cents"] - st["non_inventory_purchases_cents"]
    st["profit_cents"] = st["gross_profit_cents"] - st["expenses_cents"] - st["loss_profit_cents"]
    st["profit_estimated"] = st["sales_without_cost"] > 0
    st["expenses_by_category"] = dict(st["expenses_by_category"])
    st["business_expenses_total_cents"] = st["expenses_cents"] + st["non_inventory_purchases_cents"]
    return st


def day_stats(db, business, d: date):
    return period_stats(db, business, d, d + timedelta(days=1))


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


# ------------------------------------------------------------------ caja

def cash_position(db: Session, business: M.Business) -> dict[str, Any]:
    bal = ledger.pocket_balances(db, business.id)
    known = ledger.opening_known(db, business.id)
    upcoming = upcoming_payments(db, business, days=7)
    pending_total = sum(r["pending_cents"] for r in ledger.receivables(db, business.id))
    total_known = all(known.values())
    available = bal["efectivo"] + bal["yape"]
    missing = [p for p, k in known.items() if not k]
    out = {
        "efectivo_cents": bal["efectivo"], "yape_cents": bal["yape"], "ahorro_metas_cents": bal.get("ahorro", 0),
        "known": known, "complete": total_known, "total_cents": available,
        "receivables_cents": pending_total,
        "upcoming_payments": upcoming, "upcoming_total_cents": sum(u["amount_cents"] for u in upcoming),
        "available_for_restock_cents": available - sum(u["amount_cents"] for u in upcoming) if total_known else None,
        "missing": missing,
        "updated_at": now_lima().isoformat(),
    }
    if missing:
        names = " y ".join("efectivo" if m == "efectivo" else "Yape" for m in missing)
        out["missing_text"] = (f"Falta tu saldo inicial de {names}. Mientras tanto te muestro lo que entró y salió "
                               f"desde que registras. Dime por ejemplo «empiezo con 200 en efectivo y 150 en Yape».")
    return out


def upcoming_payments(db: Session, business: M.Business, days: int = 7, ref: date | None = None) -> list[dict[str, Any]]:
    today = ref or today_lima()
    horizon = today + timedelta(days=days)
    out = []
    month_s = month_start(today)
    paid_this_month = movements(db, business.id, *_bounds(month_s, add_months(month_s, 1)), kinds={M.EXPENSE, M.DEBT_PAYMENT})
    for fx in db.scalars(select(M.FixedExpense).where(M.FixedExpense.business_id == business.id)).all():
        if (fx.frequency or "mensual") != "mensual":
            continue   # los diarios/semanales se pagan del día a día; los anuales no tienen día del mes
        for due in _due_dates(fx.due_day, today, horizon):
            already = any(m.kind == M.EXPENSE and (m.category or "").lower() == fx.name.lower()
                          and m.occurred_at.month == due.month for m in paid_this_month) and due.month == today.month
            if not already:
                out.append({"name": fx.name, "amount_cents": fx.amount_cents, "due": due.isoformat(), "type": "gasto_fijo"})
    for d in db.scalars(select(M.Debt).where(M.Debt.business_id == business.id, M.Debt.active.is_(True))).all():
        for due in _due_dates(d.due_day, today, horizon):
            already = any(m.kind == M.DEBT_PAYMENT and m.debt_id == d.id and m.occurred_at.month == due.month
                          for m in paid_this_month) and due.month == today.month
            if not already:
                out.append({"name": f"Cuota {d.creditor}", "amount_cents": d.installment_cents, "due": due.isoformat(), "type": "cuota"})
    return sorted(out, key=lambda x: x["due"])


def _due_dates(due_day: int, today: date, horizon: date) -> list[date]:
    res = []
    for offs in (0, 1):
        m = add_months(month_start(today), offs)
        import calendar
        dd = min(due_day, calendar.monthrange(m.year, m.month)[1])
        cand = date(m.year, m.month, dd)
        if today <= cand <= horizon:
            res.append(cand)
    return res


# ------------------------------------------------------------------ productos

def product_margins(db: Session, business: M.Business, start: date, end_exclusive: date) -> list[dict[str, Any]]:
    s, e = _bounds(start, end_exclusive)
    agg: dict[int, dict[str, Any]] = {}
    for mv in movements(db, business.id, s, e, kinds={M.SALE}):
        if not mv.product_id:
            continue
        a = agg.setdefault(mv.product_id, {"product_id": mv.product_id, "name": mv.product.name, "unit": mv.product.unit, "units": 0,
                                           "revenue_cents": 0, "cost_cents": 0, "cost_known_units": 0,
                                           "discount_cents": 0, "sales": 0})
        qty = units.base_qty(mv) or 0
        a["units"] += qty
        a["revenue_cents"] += mv.amount_cents
        a["discount_cents"] += mv.discount_cents or 0
        a["sales"] += 1
        if mv.unit_cost_cents is not None and qty:
            a["cost_cents"] += round(mv.unit_cost_cents * qty)
            a["cost_known_units"] += qty
    out = []
    for a in agg.values():
        known = abs(a["cost_known_units"] - a["units"]) < 1e-6 and a["units"] > 0
        a["margin_cents"] = a["revenue_cents"] - a["cost_cents"] if known else None
        a["units"] = round(a["units"], 2)
        a["margin_per_unit_cents"] = round(a["margin_cents"] / a["units"]) if known and a["units"] else None
        a["margin_pct"] = round(100 * a["margin_cents"] / a["revenue_cents"], 1) if known and a["revenue_cents"] else None
        a["avg_price_cents"] = round(a["revenue_cents"] / a["units"]) if a["units"] else None
        a["margin_pending"] = not known
        out.append(a)
    return sorted(out, key=lambda x: (x["margin_cents"] is None, -(x["margin_cents"] or 0), -x["revenue_cents"]))


def inventory(db: Session, business: M.Business) -> list[dict[str, Any]]:
    today = today_lima()
    s, e = _bounds(today - timedelta(days=28), today + timedelta(days=1))
    sold: dict[int, float] = defaultdict(float)
    for mv in movements(db, business.id, s, e, kinds={M.SALE}):
        if mv.product_id:
            sold[mv.product_id] += units.base_qty(mv) or 0
    out = []
    for p in db.scalars(select(M.Product).where(M.Product.business_id == business.id, M.Product.active.is_(True))
                        .order_by(M.Product.name)).all():
        exp = ledger.expected_stock(db, p) if p.track_stock else None
        exp = round(exp, 2) if exp is not None else None
        if exp is not None and float(exp).is_integer():
            exp = int(exp)
        delta = ledger.stock_delta(db, p.id) if p.track_stock else None
        daily = sold[p.id] / 28
        last_count = db.scalar(select(M.Count).where(M.Count.product_id == p.id, M.Count.kind == "stock")
                               .order_by(M.Count.counted_at.desc()))
        days_left = round(exp / daily) if exp is not None and daily > 0 else None
        reorder = p.reorder_point if p.reorder_point is not None else (round(daily * 3, 1) if daily else None)
        out.append({
            "id": p.id, "name": p.name, "aliases": p.aliases, "unit": units.base_unit(p), "is_service": p.is_service,
            "spec": p.spec or {}, "spec_text": units.describe_spec(p),
            "is_input": p.is_input, "track_stock": p.track_stock,
            "price_cents": p.price_cents, "cost_cents": p.cost_cents, "initial_stock": p.initial_stock,
            "expected_stock": exp, "movement_delta": delta,
            "unit_margin_cents": (p.price_cents - p.cost_cents) if p.price_cents is not None and p.cost_cents is not None else None,
            "stock_value_cents": round(exp * p.cost_cents) if exp is not None and p.cost_cents is not None and exp > 0 else None,
            "sold_28d": round(sold[p.id], 2), "daily_avg": round(daily, 2), "days_left": days_left,
            "reorder_point": reorder,
            "needs_restock": exp is not None and reorder is not None and exp <= reorder,
            "last_count": _count_dict(last_count) if last_count else None,
            "needs_review": [x for x in (
                "Falta el stock inicial" if p.track_stock and p.initial_stock is None else None,
                "Falta el precio de venta" if p.price_cents is None and not p.is_input else None,
                "Falta el costo de compra" if p.cost_cents is None and not p.is_service else None,
                "Stock esperado negativo: revisa compras o el stock inicial" if exp is not None and exp < 0 else None,
            ) if x],
        })
    return out


def _count_dict(c: M.Count) -> dict[str, Any]:
    return {"id": c.id, "kind": c.kind, "product_id": c.product_id, "pocket": c.pocket, "counted": c.counted,
            "expected": c.expected, "difference": c.difference, "result": c.result,
            "review_status": c.review_status, "note": c.note, "counted_at": c.counted_at.isoformat()}


# ------------------------------------------------------------------ tendencias

def daily_series(db: Session, business: M.Business, days: int = 30, end: date | None = None) -> list[dict[str, Any]]:
    end = end or today_lima()
    start = end - timedelta(days=days - 1)
    s, e = _bounds(start, end + timedelta(days=1))
    by_day: dict[date, dict[str, int]] = {start + timedelta(days=i): {"sales": 0, "in": 0, "out": 0, "expenses": 0}
                                          for i in range(days)}
    for mv in movements(db, business.id, s, e):
        d = by_day.get(mv.occurred_at.date())
        if d is None:
            continue
        if mv.kind == M.SALE:
            d["sales"] += mv.amount_cents
            d["in"] += mv.paid_cents
        elif mv.kind == M.COLLECTION:
            d["in"] += mv.amount_cents
        elif mv.kind in (M.PURCHASE, M.EXPENSE, M.DEBT_PAYMENT):
            d["out"] += mv.paid_cents
            d["expenses"] += mv.paid_cents
        elif mv.kind == M.WITHDRAWAL:
            d["out"] += mv.amount_cents
        elif mv.kind == M.CONTRIBUTION:
            d["in"] += mv.amount_cents
    return [{"date": d.isoformat(), "label": f"{DIAS[d.weekday()][:2]} {d.day}", "sales_cents": v["sales"],
             "inflow_cents": v["in"], "outflow_cents": v["out"], "net_cents": v["in"] - v["out"]}
            for d, v in sorted(by_day.items())]


def weekday_pattern(db: Session, business: M.Business, weeks: int = 8) -> dict[str, Any]:
    end = today_lima()
    start = end - timedelta(days=weeks * 7)
    series = daily_series(db, business, days=weeks * 7, end=end - timedelta(days=1))
    by_wd: dict[int, list[int]] = defaultdict(list)
    for row in series:
        d = date.fromisoformat(row["date"])
        if d >= start:
            by_wd[d.weekday()].append(row["sales_cents"])
    avgs = {wd: (sum(v) / len(v) if v else 0) for wd, v in by_wd.items()}
    if not avgs or not any(avgs.values()):
        return {"available": False, "days": []}
    overall = sum(avgs.values()) / len(avgs)
    days = [{"weekday": wd, "name": DIAS[wd], "avg_sales_cents": round(a),
             "vs_avg_pct": round(100 * (a - overall) / overall) if overall else 0} for wd, a in sorted(avgs.items())]
    best = max(days, key=lambda x: x["avg_sales_cents"])
    worst = min(days, key=lambda x: x["avg_sales_cents"])
    return {"available": True, "days": days, "best": best, "worst": worst, "overall_avg_cents": round(overall)}


def month_trend(db: Session, business: M.Business, ref: date | None = None) -> dict[str, Any]:
    today = ref or today_lima()
    ms = month_start(today)
    prev = add_months(ms, -1)
    n = today.day
    cur = period_stats(db, business, ms, today + timedelta(days=1))
    import calendar
    prev_end_day = min(n, calendar.monthrange(prev.year, prev.month)[1])
    prv = period_stats(db, business, prev, date(prev.year, prev.month, prev_end_day) + timedelta(days=1))
    pct = round(100 * (cur["sales_cents"] - prv["sales_cents"]) / prv["sales_cents"]) if prv["sales_cents"] else None
    return {"current_sales_cents": cur["sales_cents"], "previous_same_days_cents": prv["sales_cents"],
            "pct": pct, "direction": None if pct is None else ("mejor" if pct > 3 else "peor" if pct < -3 else "igual"),
            "days_compared": n, "current_profit_cents": cur["profit_cents"], "previous_profit_cents": prv["profit_cents"]}


def cost_alerts(db: Session, business: M.Business, ref: date | None = None) -> list[dict[str, Any]]:
    """«Ojo: el aceite subió 15% vs la semana pasada»: compara costo unitario de compra."""
    today = ref or today_lima()
    s, e = _bounds(today - timedelta(days=21), today + timedelta(days=1))
    last_week_start = today - timedelta(days=7)
    per: dict[int, dict[str, list[int]]] = defaultdict(lambda: {"recent": [], "before": []})
    for mv in movements(db, business.id, s, e, kinds={M.PURCHASE}):
        if mv.product_id and mv.unit_cost_cents:
            key = "recent" if mv.occurred_at.date() > last_week_start else "before"
            per[mv.product_id][key].append(mv.unit_cost_cents)
    out = []
    for pid, v in per.items():
        if v["recent"] and v["before"]:
            new, old = v["recent"][-1], sum(v["before"]) / len(v["before"])
            pct = round(100 * (new - old) / old)
            if abs(pct) >= 8:
                p = db.get(M.Product, pid)
                out.append({"product": p.name, "pct": pct, "new_cost_cents": new, "old_cost_cents": round(old)})
    return out


# ------------------------------------------------------------------ equilibrio y rotación

def declared_costs(db: Session, business: M.Business) -> dict[str, int]:
    """Gastos que la persona dijo que paga, llevados a «cuánto es al mes» según su frecuencia."""
    from .costs import monthly_cents
    out = {"fijo": 0, "variable": 0}
    for f in db.scalars(select(M.FixedExpense).where(M.FixedExpense.business_id == business.id)).all():
        out["fijo" if (f.cost_type or "fijo") == "fijo" else "variable"] += monthly_cents(f.amount_cents, f.frequency)
    return out


def monthly_fixed_costs(db: Session, business: M.Business) -> int:
    declared = declared_costs(db, business)["fijo"]
    if declared:
        return declared
    today = today_lima()
    last = period_stats(db, business, today - timedelta(days=30), today + timedelta(days=1))
    return last["fixed_expenses_cents"]


def break_even(db: Session, business: M.Business) -> dict[str, Any]:
    today = today_lima()
    st = period_stats(db, business, today - timedelta(days=30), today + timedelta(days=1))
    fixed = monthly_fixed_costs(db, business)
    if st["sales_cents"] <= 0:
        return {"available": False, "reason": "Aún no hay ventas suficientes para calcularlo.", "fixed_cents": fixed}
    variable = st["cogs_cents"] + st["non_inventory_purchases_cents"] + st["variable_expenses_cents"]
    declared_var = declared_costs(db, business)["variable"]
    if declared_var and not st["variable_expenses_cents"]:
        # aún no registra sus gastos variables (bolsas, flete): uso lo que dijo, en proporción a los días con datos
        first = db.scalar(select(func.min(M.Movement.occurred_at)).where(M.Movement.business_id == business.id))
        days = min(30, max(1, (today - first.date()).days + 1)) if first else 30
        variable += round(declared_var * days / 30)
    cm_ratio = 1 - variable / st["sales_cents"]
    if cm_ratio <= 0:
        return {"available": False, "reason": "Tus costos están por encima de tus ventas: revisa precios y costos.", "fixed_cents": fixed}
    be = round(fixed / cm_ratio)
    return {"available": True, "fixed_cents": fixed, "variable_declared_cents": declared_costs(db, business)["variable"],
            "contribution_margin_pct": round(cm_ratio * 100, 1),
            "break_even_monthly_cents": be, "break_even_daily_cents": round(be / 30),
            "last30_sales_cents": st["sales_cents"],
            "coverage_pct": round(100 * st["sales_cents"] / be) if be else None,
            "estimated": st["profit_estimated"]}


def rotation(db: Session, business: M.Business) -> dict[str, Any]:
    today = today_lima()
    st = period_stats(db, business, today - timedelta(days=30), today + timedelta(days=1))
    cash = cash_position(db, business)
    daily_out = st["outflow_cents"] / 30 if st["outflow_cents"] else 0
    inv = inventory(db, business)
    inv_value = sum(i["stock_value_cents"] or 0 for i in inv)
    out = {
        "cash_days": round(cash["total_cents"] / daily_out) if daily_out and cash["complete"] else None,
        "cash_turnover": round(st["collected_cents"] / cash["total_cents"], 1) if cash["complete"] and cash["total_cents"] > 0 else None,
        "inventory_value_cents": inv_value,
        "inventory_turnover_30d": round(st["cogs_cents"] / inv_value, 2) if inv_value else None,
        "inventory_days": round(inv_value / (st["cogs_cents"] / 30)) if st["cogs_cents"] and inv_value else None,
        "receivable_days": None,
    }
    rec = cash["receivables_cents"]
    if st["sales_cents"]:
        out["receivable_days"] = round(rec / (st["sales_cents"] / 30))
    return out


# ------------------------------------------------------------------ metas

def goals(db: Session, business: M.Business) -> list[dict[str, Any]]:
    today = today_lima()
    st30 = period_stats(db, business, today - timedelta(days=30), today + timedelta(days=1))
    daily_profit = st30["profit_cents"] / 30 if st30["profit_cents"] > 0 else 0
    cash = cash_position(db, business)
    out = []
    for g in db.scalars(select(M.Goal).where(M.Goal.business_id == business.id, M.Goal.status != "cancelada")
                        .order_by(M.Goal.created_at)).all():
        out.append(goal_status(db, business, g, cash=cash, daily_profit=daily_profit, today=today))
    return out


def goal_status(db: Session, business: M.Business, g: M.Goal, *, cash=None, daily_profit: float = 0,
                today: date | None = None) -> dict[str, Any]:
    today = today or today_lima()
    cash = cash or cash_position(db, business)
    saved = sum(m.amount_cents for m in movements(db, business.id, kinds={M.GOAL_SAVING}) if m.goal_id == g.id)
    d: dict[str, Any] = {"id": g.id, "kind": g.kind, "name": g.name, "target_cents": g.target_cents,
                         "deadline": g.deadline.isoformat() if g.deadline else None, "status": g.status,
                         "product_id": g.product_id, "quantity": g.quantity}
    if g.kind == "reposicion":
        avail = cash["available_for_restock_cents"]
        d["available_cents"] = avail
        d["upcoming_total_cents"] = cash["upcoming_total_cents"]
        if avail is None:
            d["complete_info"] = False
            d["message"] = (f"Tu próxima compra cuesta {soles(g.target_cents)}. Para decirte cuánto puedes usar, "
                            f"necesito tu saldo inicial de {' y '.join(cash['missing'])}.")
            d["progress_pct"] = None
            d["missing_cents"] = None
        else:
            usable = max(0, avail)
            missing = max(0, g.target_cents - usable)
            d["complete_info"] = True
            d["missing_cents"] = missing
            d["progress_pct"] = min(100, round(100 * usable / g.target_cents)) if g.target_cents else 100
            pagos = " y tus pagos registrados" if cash["upcoming_payments"] else ""
            if missing:
                d["message"] = (f"Tu próxima compra cuesta {soles(g.target_cents)}. Según tu caja{pagos}, hoy tienes "
                                f"{soles(usable)} disponibles. Te faltan {soles(missing)}.")
            else:
                d["message"] = (f"Tu próxima compra cuesta {soles(g.target_cents)}. Según tu caja{pagos}, hoy tienes "
                                f"{soles(usable)} disponibles. ¡Ya te alcanza para reponer!")
    else:
        d["saved_cents"] = saved
        remaining = max(0, g.target_cents - saved)
        d["missing_cents"] = remaining
        d["progress_pct"] = min(100, round(100 * saved / g.target_cents)) if g.target_cents else 100
        if g.deadline:
            days_left = max(1, (g.deadline - today).days)
            per_day = remaining / days_left
            d["days_left"] = days_left
            d["per_day_cents"] = round(per_day)
            d["per_week_cents"] = round(per_day * 7)
            total_days = max(1, (g.deadline - g.created_at.date()).days)
            elapsed = max(0, (today - g.created_at.date()).days)
            expected = g.target_cents * min(1, elapsed / total_days)
            d["expected_cents"] = round(expected)
            d["behind"] = saved + 1 < expected * 0.9
            d["feasible"] = daily_profit >= per_day if daily_profit else None
            msg = (f"Para tu meta «{g.name}» te faltan {soles(remaining)}. Separa {soles(round(per_day * 7))} por semana "
                   f"(unos {soles(round(per_day))} al día).")
            if d["behind"]:
                msg += f" Vas atrasada: a estas alturas deberías llevar {soles(round(expected))}."
            if daily_profit and per_day > daily_profit:
                msg += f" Ojo: ganas unos {soles(round(daily_profit))} al día; quizá conviene mover la fecha."
            d["message"] = msg
        else:
            d["message"] = f"Llevas {soles(saved)} de {soles(g.target_cents)} para «{g.name}»."
    return d


# ------------------------------------------------------------------ consejos

def pack_savings(db: Session, business: M.Business, days: int = 28) -> list[dict[str, Any]]:
    """Cuánto ahorraría por semana si comprara por jaba/saco en vez de por kilo (según sus propias compras)."""
    today = today_lima()
    s, e = _bounds(today - timedelta(days=days), today + timedelta(days=1))
    by: dict[int, dict[str, float]] = defaultdict(lambda: {"kg": 0.0, "cost": 0.0})
    for mv in movements(db, business.id, s, e, kinds={M.PURCHASE}):
        p = mv.product
        if not p:
            continue
        c = (p.spec or {}).get("compra_por") or {}
        if not c.get("equivale") or not c.get("costo_cents") or mv.measure_unit == c.get("unidad"):
            continue
        q = units.base_qty(mv)
        if q:
            by[p.id]["kg"] += q
            by[p.id]["cost"] += mv.amount_cents
    out = []
    for pid, v in by.items():
        p = db.get(M.Product, pid)
        c = p.spec["compra_por"]
        pack_unit = c["costo_cents"] / c["equivale"]
        paid_unit = v["cost"] / v["kg"]
        if paid_unit > pack_unit * 1.03:
            weekly = (paid_unit - pack_unit) * v["kg"] / (days / 7)
            out.append({"product": p.name, "pack": c["unidad"], "weekly_cents": round(weekly),
                        "paid_unit_cents": round(paid_unit), "pack_unit_cents": round(pack_unit)})
    return sorted(out, key=lambda x: -x["weekly_cents"])


def _next_weekday_name(today: date, wd: int) -> str:
    return DIAS[wd] if today.weekday() != wd else f"el próximo {DIAS[wd]}"


def advice(db: Session, business: M.Business) -> list[str]:
    """Consejos con sus propios números (no genéricos)."""
    today = today_lima()
    tips: list[str] = []
    # 1. comprar por jaba/saco
    for sv in pack_savings(db, business)[:1]:
        if sv["weekly_cents"] >= 300:
            tips.append(f"Si compras el {sv['product'].lower()} por {sv['pack']} y no por kilo, ahorras unos {soles(sv['weekly_cents'])} por semana "
                        f"(te sale a {soles(sv['pack_unit_cents'])} el kilo en vez de {soles(sv['paid_unit_cents'])}).")
    # 2. fiados con nombre y fecha
    rec = ledger.receivables(db, business.id)
    total_rec = sum(r["pending_cents"] for r in rec)
    if total_rec >= 5000:
        oldest = min(rec, key=lambda r: r["occurred_at"])
        days = (today - datetime.fromisoformat(oldest["occurred_at"]).date()).days
        tips.append(f"Tus fiados ya suman {soles(total_rec)}: cobra a {oldest['counterparty']} ({soles(oldest['pending_cents'])}, hace {days} días) "
                    f"antes del {_next_weekday_name(today, 4)}.")
    # 3. qué producto te deja más
    margins = [m for m in product_margins(db, business, today - timedelta(days=30), today + timedelta(days=1))
               if m["margin_per_unit_cents"] is not None and m["units"] >= 3]
    if len(margins) >= 2:
        best = max(margins, key=lambda m: m["margin_per_unit_cents"])
        worst = min(margins, key=lambda m: m["margin_per_unit_cents"])
        if best["product_id"] != worst["product_id"]:
            ub = "kilo" if best.get("unit") == "kg" else (best.get("unit") or "unidad")
            uw = "kilo" if worst.get("unit") == "kg" else (worst.get("unit") or "unidad")
            tips.append(f"{best['name']} te deja {soles(best['margin_per_unit_cents'])} por {ub} y "
                        f"{worst['name'].lower()} solo {soles(worst['margin_per_unit_cents'])} por {uw}: ofrece más {best['name'].lower()}.")
        top_seller = max(margins, key=lambda m: m["revenue_cents"])
        best_total = max(margins, key=lambda m: m["margin_cents"] or 0)
        if top_seller["product_id"] != best_total["product_id"]:
            tips.append(f"Lo que más vendes es {top_seller['name'].lower()}, pero lo que más plata te deja es {best_total['name'].lower()}.")
    # 4. pérdidas por producto
    s30, e30 = _bounds(today - timedelta(days=30), today + timedelta(days=1))
    loss_by: dict[str, int] = defaultdict(int)
    for mv in movements(db, business.id, s30, e30, kinds={M.LOSS}):
        loss_by[(mv.product.name if mv.product else (mv.description or "otros")).lower()] += mv.amount_cents
    if loss_by:
        name, amt = max(loss_by.items(), key=lambda x: x[1])
        if amt >= 2000:
            tips.append(f"En 30 días se te malogró {soles(amt)} de {name}: compra un poco menos o véndelo con oferta en la tarde.")
    # 5. días flojos
    wp = weekday_pattern(db, business)
    if wp["available"] and wp["worst"]["vs_avg_pct"] <= -20:
        prev_day = DIAS[(wp["worst"]["weekday"] - 1) % 7]
        verb = f"el {prev_day} compra menos" if business.kind in ("verduras", "reventa") else "ese día prepara menos"
        tips.append(f"Los {weekday_plural(wp['worst']['name'])} vendes {abs(wp['worst']['vs_avg_pct'])}% menos: {verb}.")
    # 6. stock que se acaba
    for i in inventory(db, business):
        if i["track_stock"] and i["days_left"] is not None and i["days_left"] <= 1 and i["expected_stock"] is not None:
            u = "kg" if i["unit"] == "kg" else units.unit_name(i["unit"], i["expected_stock"])
            tips.append(f"Mañana compra más {i['name'].lower()}: te quedan {units.fmt_qty(max(0, i['expected_stock']))} {u}, te alcanza para un día.")
            break
    # 7. costos que subieron
    for a in cost_alerts(db, business):
        if a["pct"] >= 8:
            tips.append(f"{a['product']} te costó {a['pct']}% más que la semana pasada: sube un poco tu precio o busca otro puesto en el mayorista.")
            break
    # 8. casa y negocio / metas
    month = period_stats(db, business, month_start(today), today + timedelta(days=1))
    gs = [g for g in goals(db, business) if g["kind"] == "ahorro" and g["status"] == "activa"]
    if gs and gs[0].get("behind") and month["withdrawals_cents"]:
        tips.append(f"Este mes sacaste {soles(month['withdrawals_cents'])} para la casa y vas atrasada con «{gs[0]['name']}»: "
                    f"separa {soles(gs[0].get('per_week_cents'))} esta semana.")
    # 9. descuentos
    if month["sales_cents"] and month["discounts_cents"] > month["sales_cents"] * 0.08:
        tips.append(f"Este mes diste {soles(month['discounts_cents'])} en descuentos ({round(100 * month['discounts_cents'] / month['sales_cents'])}% de tus ventas): cuida tu ganancia.")
    if not tips:
        tips.append("Sigue mandando tus ventas todos los días: con una semana de datos te doy consejos con tus propios números.")
    return tips


# ------------------------------------------------------------------ panel

def dashboard(db: Session, business: M.Business) -> dict[str, Any]:
    today = today_lima()
    day = day_stats(db, business, today)
    wk = period_stats(db, business, week_start(today), today + timedelta(days=1))
    ms = month_start(today)
    month = period_stats(db, business, ms, today + timedelta(days=1))
    cash = cash_position(db, business)
    return {
        "business": {"id": business.id, "name": business.name, "kind": business.kind, "demo": business.demo,
                     "owner_name": business.owner_name},
        "today": today.isoformat(), "updated_at": now_lima().isoformat(),
        "day": day, "week": wk, "month": month, "cash": cash,
        "receivables": ledger.receivables(db, business.id),
        "series": daily_series(db, business, 30),
        "weekday": weekday_pattern(db, business),
        "trend": month_trend(db, business),
        "margins": product_margins(db, business, today - timedelta(days=30), today + timedelta(days=1)),
        "break_even": break_even(db, business),
        "rotation": rotation(db, business),
        "goals": goals(db, business),
        "alerts": cost_alerts(db, business),
        "advice": advice(db, business),
        "inventory_flags": [i for i in inventory(db, business) if i["needs_review"] or i["needs_restock"]],
    }


def weekly_series(db: Session, business: M.Business, start: date, end_exclusive: date) -> list[dict[str, Any]]:
    out = []
    ws = week_start(start)
    while ws < end_exclusive:
        we = ws + timedelta(days=7)
        st = period_stats(db, business, max(ws, start), min(we, end_exclusive))
        out.append({"week_start": ws.isoformat(), "sales_cents": st["sales_cents"], "net_cents": st["net_cashflow_cents"],
                    "active_days": st["active_days"]})
        ws = we
    return out


def cv(values: list[int]) -> float | None:
    vals = [v for v in values]
    if len(vals) < 2 or statistics.mean(vals) == 0:
        return None
    return statistics.pstdev(vals) / statistics.mean(vals)


__all__ = ["period_stats", "day_stats", "cash_position", "dashboard", "goals", "advice", "inventory",
           "product_margins", "break_even", "rotation", "weekday_pattern", "month_trend", "daily_series",
           "weekly_series", "cv", "day_bounds"]
