"""Reporte de ingresos y capacidad de pago para presentar a BCP o a una caja.

Es un insumo para una futura evaluación: no hay scoring crediticio ni aprobación.
"""
from __future__ import annotations

import statistics
from collections import Counter
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import ledger, metrics, reconcile
from . import models as M
from .timeutil import add_months, month_label, month_start, now_lima, today_lima

ORIGIN_LABEL = {"autodeclarado": "Autodeclarado", "con_adjunto": "Con adjunto", "respaldo_yape": "Respaldo Yape",
                "comprobante": "Comprobante de proveedor"}
CHECK_LABEL = {"consistente": "Consistente", "diferencia": "Con diferencia", "sin_datos": "Sin datos suficientes"}


def _months(start: date, end_exclusive: date) -> list[tuple[date, date]]:
    out = []
    m = month_start(start)
    while m < end_exclusive:
        nxt = add_months(m, 1)
        out.append((max(m, start), min(nxt, end_exclusive)))
        m = nxt
    return out


def monthly_rows(db: Session, b: M.Business, start: date, end_exclusive: date) -> list[dict[str, Any]]:
    rows = []
    for s, e in _months(start, end_exclusive):
        st = metrics.period_stats(db, b, s, e)
        days = (e - s).days
        net_business = st["collected_cents"] - st["purchases_cents"] - st["expenses_cents"]
        net_total = net_business - st["withdrawals_cents"] - st["debt_payments_cents"]
        rows.append({
            "month": s.strftime("%Y-%m"), "label": month_label(s), "days": days,
            "full_month": s.day == 1 and e == add_months(month_start(s), 1),
            "sales_cents": st["sales_cents"], "collected_cents": st["collected_cents"],
            "collected_by_method": st["collected_by_method"], "new_credit_cents": st["new_credit_cents"],
            "collections_cents": st["collections_cents"],
            "discounts_cents": st["discounts_cents"], "purchases_cents": st["purchases_cents"],
            "expenses_cents": st["expenses_cents"], "withdrawals_cents": st["withdrawals_cents"],
            "contributions_cents": st["contributions_cents"], "debt_payments_cents": st["debt_payments_cents"],
            "profit_cents": st["profit_cents"], "net_business_cents": net_business, "net_cents": net_total,
            "active_days": st["active_days"],
        })
    return rows


def capacity(db: Session, b: M.Business, start: date | None = None, end_exclusive: date | None = None) -> dict[str, Any]:
    today = today_lima()
    end_exclusive = end_exclusive or today + timedelta(days=1)
    start = start or add_months(month_start(today), -3)
    rows = monthly_rows(db, b, start, end_exclusive)
    full = [r for r in rows if r["full_month"]] or rows
    full = [r for r in full if r["active_days"] > 0]
    if not full:
        return {"months_used": 0, "avg_net_cents": None, "worst_net_cents": None,
                "suggested_max_installment_cents": None, "rule": None}
    # normaliza meses incompletos a 30 días
    nets = [round(r["net_cents"] * 30 / r["days"]) for r in full]
    avg = round(statistics.mean(nets))
    worst = min(nets)
    suggested = max(0, min(round(avg * 0.4), round(worst * 0.7))) if avg > 0 else 0
    return {"months_used": len(full), "avg_net_cents": avg, "worst_net_cents": worst,
            "avg_sales_cents": round(statistics.mean(round(r["sales_cents"] * 30 / r["days"]) for r in full)),
            "suggested_max_installment_cents": suggested,
            "rule": "Hasta 40% del flujo neto mensual promedio, sin pasar el 70% del peor mes.",
            "current_debt_installments_cents": sum(d.installment_cents for d in db.scalars(
                select(M.Debt).where(M.Debt.business_id == b.id, M.Debt.active.is_(True))).all())}


def build(db: Session, b: M.Business, start: date | None = None, end: date | None = None) -> dict[str, Any]:
    today = today_lima()
    end = end or today
    start = start or add_months(month_start(today), -2)
    end_x = end + timedelta(days=1)
    s_dt, e_dt = datetime(start.year, start.month, start.day), datetime(end_x.year, end_x.month, end_x.day)
    st = metrics.period_stats(db, b, start, end_x)
    rows = monthly_rows(db, b, start, end_x)
    cap = capacity(db, b, start, end_x)
    weeks = metrics.weekly_series(db, b, start, end_x)
    wsales = [w["sales_cents"] for w in weeks if w["active_days"] > 0]
    cv = metrics.cv(wsales)
    w2w = [abs(wsales[i] - wsales[i - 1]) / wsales[i - 1] for i in range(1, len(wsales)) if wsales[i - 1]]
    stability = {
        "weekly": weeks, "cv": round(cv, 2) if cv is not None else None,
        "avg_week_change_pct": round(100 * statistics.mean(w2w)) if w2w else None,
        "min_week_cents": min(wsales) if wsales else None, "max_week_cents": max(wsales) if wsales else None,
        "label": None if cv is None else ("Ventas parejas" if cv < 0.2 else "Variación moderada" if cv < 0.4 else "Ventas a saltos"),
        "weekday": metrics.weekday_pattern(db, b),
    }

    all_mvs = metrics.movements(db, b.id)
    first = all_mvs[0].occurred_at.date() if all_mvs else None
    months_active = sorted({m.occurred_at.strftime("%Y-%m") for m in all_mvs})
    consecutive = 0
    cursor = month_start(today)
    while cursor.strftime("%Y-%m") in months_active:
        consecutive += 1
        cursor = add_months(cursor, -1)
    period_days = (end_x - start).days
    seniority = {
        "first_record": first.isoformat() if first else None,
        "months_with_records": len(months_active), "consecutive_months": consecutive,
        "active_days": st["active_days"], "period_days": period_days,
        "active_days_pct": round(100 * st["active_days"] / period_days) if period_days else None,
        "avg_active_days_per_month": round(statistics.mean([r["active_days"] * 30 / r["days"] for r in rows]), 1) if rows else None,
    }

    mvs = metrics.movements(db, b.id, s_dt, e_dt)
    sales = [m for m in mvs if m.kind == M.SALE]
    purchases = [m for m in mvs if m.kind == M.PURCHASE]
    goals = metrics.goals(db, b)
    savings_goals = [g for g in goals if g["kind"] == "ahorro"]
    debts = db.scalars(select(M.Debt).where(M.Debt.business_id == b.id)).all()
    debt_months = []
    for d in debts:
        for r in rows:
            if not r["full_month"]:
                continue
            y, mo = map(int, r["month"].split("-"))
            pays = [m for m in mvs if m.kind == M.DEBT_PAYMENT and m.debt_id == d.id and m.occurred_at.year == y
                    and m.occurred_at.month == mo]
            on_time = any(m.occurred_at.day <= d.due_day + 2 for m in pays)
            debt_months.append({"creditor": d.creditor, "month": r["label"], "paid": bool(pays), "on_time": on_time})
    discipline = {
        "daily_record_pct": seniority["active_days_pct"],
        "withdrawals_registered": sum(1 for m in mvs if m.kind == M.WITHDRAWAL),
        "withdrawals_pct_of_sales": round(100 * st["withdrawals_cents"] / st["sales_cents"]) if st["sales_cents"] else None,
        "separates_home_business": any(m.kind == M.WITHDRAWAL for m in mvs),
        "suppliers_paid_on_purchase_pct": round(100 * sum(1 for p in purchases if p.paid_cents >= p.amount_cents) / len(purchases)) if purchases else None,
        "debt_payments": debt_months,
        "debt_on_time_pct": round(100 * sum(1 for x in debt_months if x["on_time"]) / len(debt_months)) if debt_months else None,
        "goals": [{"name": g["name"], "kind": g["kind"], "progress_pct": g.get("progress_pct"), "behind": g.get("behind")} for g in goals],
        "savings_goals_on_track": sum(1 for g in savings_goals if not g.get("behind")),
        "savings_goals_total": len(savings_goals),
    }

    inv = metrics.inventory(db, b)
    assets = db.scalars(select(M.Asset).where(M.Asset.business_id == b.id)).all()
    known = ledger.opening_known(db, b.id)
    avg_cash = None
    if all(known.values()):
        samples = []
        d = start
        while d <= end:
            bal = ledger.pocket_balances(db, b.id, until=datetime(d.year, d.month, d.day) + timedelta(days=1))
            samples.append(bal["efectivo"] + bal["yape"])
            d += timedelta(days=1)
        avg_cash = round(statistics.mean(samples)) if samples else None
    capital = {
        "inventory_value_cents": sum(i["stock_value_cents"] or 0 for i in inv),
        "inventory_items": [{"name": i["name"], "units": i["expected_stock"], "value_cents": i["stock_value_cents"]}
                            for i in inv if i["track_stock"]],
        "assets": [{"name": a.name, "value_cents": a.value_cents} for a in assets],
        "assets_value_cents": sum(a.value_cents for a in assets),
        "avg_cash_cents": avg_cash,
        "cash_now": metrics.cash_position(db, b),
    }

    yapes = db.scalars(select(M.YapePayment).where(M.YapePayment.business_id == b.id,
                                                   M.YapePayment.received_at >= s_dt, M.YapePayment.received_at < e_dt)).all()
    payer_counts = Counter(y.payer for y in yapes)
    payer_amounts: Counter = Counter()
    for y in yapes:
        payer_amounts[y.payer] += y.amount_cents
    total_y = sum(payer_amounts.values())
    diversification = {
        "distinct_yape_payers": len(payer_counts),
        "yape_payments": len(yapes),
        "top_payer_share_pct": round(100 * max(payer_amounts.values()) / total_y) if total_y else None,
        "distinct_credit_customers": len({m.counterparty for m in sales if m.amount_cents > m.paid_cents and m.counterparty}),
    }
    backed = sum(m.amount_cents for m in sales if m.origin == "respaldo_yape")
    yape_declared = sum(m.paid_cents for m in sales if m.method == "yape")
    reliability = {
        "sales_backed_pct": round(100 * backed / st["sales_cents"]) if st["sales_cents"] else None,
        "yape_sales_backed_pct": round(100 * sum(m.paid_cents for m in sales if m.origin == "respaldo_yape") / yape_declared) if yape_declared else None,
        "backed_sales_cents": backed,
        "purchases_with_receipt": sum(1 for p in purchases if p.origin in ("comprobante", "con_adjunto")),
        "purchases_total": len(purchases),
        "attachments": sum(len(m.attachments) for m in mvs),
        "by_origin": dict(Counter(ORIGIN_LABEL.get(m.origin, m.origin) for m in sales + purchases)),
    }

    counts = db.scalars(select(M.Count).where(M.Count.business_id == b.id, M.Count.counted_at >= s_dt,
                                              M.Count.counted_at < e_dt).order_by(M.Count.counted_at)).all()
    obs = []
    for c in counts:
        name = db.get(M.Product, c.product_id).name if c.product_id else f"Caja {c.pocket}"
        obs.append({"date": c.counted_at.date().isoformat(), "item": name, "kind": c.kind, "counted": c.counted,
                    "expected": c.expected, "difference": c.difference, "result": CHECK_LABEL[c.result],
                    "review_status": c.review_status, "note": c.note})
    detail = []
    for m in mvs:
        if m.kind in (M.OPENING,):
            continue
        detail.append({
            "id": m.id, "date": m.occurred_at.isoformat(), "kind": m.kind,
            "product": m.product.name if m.product else None, "quantity": m.quantity,
            "reference_total_cents": m.reference_total_cents, "discount_cents": m.discount_cents,
            "amount_cents": m.amount_cents, "paid_cents": m.paid_cents, "method": m.method,
            "category": m.category, "counterparty": m.counterparty,
            "origin": ORIGIN_LABEL.get(m.origin, m.origin),
            "check": CHECK_LABEL[reconcile.sale_check(db, m)] if m.kind in (M.SALE, M.PURCHASE) else None,
            "revision": m.revision, "demo": m.demo,
        })
    consent = db.scalars(select(M.ReportConsent).where(M.ReportConsent.business_id == b.id)
                         .order_by(M.ReportConsent.month.desc())).all()
    return {
        "business": {"id": b.id, "name": b.name, "owner_name": b.owner_name, "kind": b.kind, "description": b.description,
                     "demo": b.demo, "created_at": b.created_at.isoformat()},
        "generated_at": now_lima().isoformat(), "period": {"start": start.isoformat(), "end": end.isoformat()},
        "demo_data": b.demo or any(m.demo for m in mvs),
        "summary": {
            "sales_cents": st["sales_cents"], "collected_by_method": st["collected_by_method"],
            "collected_cents": st["collected_cents"], "collections_cents": st["collections_cents"],
            "new_credit_cents": st["new_credit_cents"],
            "discounts_cents": st["discounts_cents"], "discount_sales": st["discount_sales"],
            "purchases_cents": st["purchases_cents"], "expenses_cents": st["expenses_cents"],
            "expenses_by_category": st["expenses_by_category"],
            "withdrawals_cents": st["withdrawals_cents"], "contributions_cents": st["contributions_cents"],
            "debt_payments_cents": st["debt_payments_cents"], "transfers_cents": st["transfers_cents"],
            "profit_cents": st["profit_cents"], "active_days": st["active_days"],
            "net_cashflow_cents": st["net_cashflow_cents"],
        },
        "months": rows, "capacity": cap, "stability": stability, "seniority": seniority, "discipline": discipline,
        "capital": capital, "diversification": diversification, "reliability": reliability,
        "receivables": ledger.receivables(db, b.id),
        "margins": metrics.product_margins(db, b, start, end_x),
        "break_even": metrics.break_even(db, b),
        "reconciliation": {"observations": obs,
                           "open": [o for o in obs if o["result"] != "Consistente" and o["review_status"] in ("abierto", "pendiente")]},
        "movements": detail,
        "consents": [{"month": c.month, "decision": c.decision, "decided_at": c.decided_at.isoformat()} for c in consent],
        "disclaimer": ("Reporte elaborado con registros de la emprendedora. Es un insumo para una evaluación futura y no "
                       "constituye calificación crediticia, aprobación de préstamo ni conexión bancaria."),
    }


# ====================================================================== informe BCP (solo Yape verificado)

KIND_LABEL = {M.SALE: "Venta", M.COLLECTION: "Cobro de fiado", M.PURCHASE: "Compra de mercadería", M.EXPENSE: "Gasto del negocio",
              M.DEBT_PAYMENT: "Pago de cuota", M.WITHDRAWAL: "Gasto personal"}


def build_bcp(db: Session, b: M.Business, start: date | None = None, end: date | None = None) -> dict[str, Any]:
    """Informe mensual para BCP: solo ingresos y egresos por Yape verificados contra el registro de Yape.

    El efectivo y los movimientos por Yape sin verificar no entran."""
    today = today_lima()
    end = end or today
    start = start or add_months(month_start(today), -2)
    end_x = end + timedelta(days=1)
    s_dt, e_dt = datetime(start.year, start.month, start.day), datetime(end_x.year, end_x.month, end_x.day)
    mvs = metrics.movements(db, b.id, s_dt, e_dt, kinds=set(M.YAPE_IN_KINDS) | set(M.YAPE_OUT_KINDS))
    yape_mvs = [m for m in mvs if m.method == "yape" and m.paid_cents]
    links = {y.movement_id: y for y in db.scalars(select(M.YapePayment).where(
        M.YapePayment.business_id == b.id, M.YapePayment.movement_id.is_not(None))).all()}
    verified = [m for m in yape_mvs if m.id in links]
    pending = [m for m in yape_mvs if m.id not in links]

    def is_in(m):
        return m.kind in M.YAPE_IN_KINDS

    # por mes
    rows = []
    for s, e in _months(start, end_x):
        ms = [m for m in verified if s <= m.occurred_at.date() < e]
        inc = sum(m.paid_cents for m in ms if is_in(m))
        biz_out = sum(m.paid_cents for m in ms if m.kind in (M.PURCHASE, M.EXPENSE))
        debt = sum(m.paid_cents for m in ms if m.kind == M.DEBT_PAYMENT)
        pers = sum(m.paid_cents for m in ms if m.kind == M.WITHDRAWAL)
        days = (e - s).days
        rows.append({"month": s.strftime("%Y-%m"), "label": month_label(s), "days": days,
                     "full_month": s.day == 1 and e == add_months(month_start(s), 1),
                     "income_cents": inc, "business_out_cents": biz_out, "debt_cents": debt, "personal_cents": pers,
                     "out_cents": biz_out + debt + pers, "net_cents": inc - biz_out - debt - pers,
                     "operations": len(ms), "active_days": len({m.occurred_at.date() for m in ms})})
    used = [r for r in rows if r["full_month"] and r["operations"]] or [r for r in rows if r["operations"]]
    nets = [round(r["net_cents"] * 30 / r["days"]) for r in used]
    incs = [round(r["income_cents"] * 30 / r["days"]) for r in used]
    avg_net = round(statistics.mean(nets)) if nets else None
    worst = min(nets) if nets else None
    suggested = max(0, min(round(avg_net * 0.4), round(worst * 0.7))) if avg_net and avg_net > 0 else (0 if nets else None)
    debts = db.scalars(select(M.Debt).where(M.Debt.business_id == b.id, M.Debt.active.is_(True))).all()

    # estabilidad semanal de ingresos verificados
    weeks = []
    ws = metrics.week_start(start)
    while ws < end_x:
        we = ws + timedelta(days=7)
        weeks.append({"week_start": ws.isoformat(), "income_cents": sum(m.paid_cents for m in verified if is_in(m) and ws <= m.occurred_at.date() < we)})
        ws = we
    winc = [w["income_cents"] for w in weeks if w["income_cents"] > 0]
    cv = metrics.cv(winc)

    payers = Counter()
    for m in verified:
        if is_in(m):
            payers[links[m.id].payer] += m.paid_cents
    tot_in = sum(payers.values())
    period_days = (end_x - start).days
    active = len({m.occurred_at.date() for m in verified})
    months_all = sorted({m.occurred_at.strftime("%Y-%m") for m in metrics.movements(db, b.id) if m.method == "yape" and m.id in links})
    consecutive, cursor = 0, month_start(today)
    while cursor.strftime("%Y-%m") in months_all:
        consecutive += 1
        cursor = add_months(cursor, -1)
    debt_pays = [m for m in verified if m.kind == M.DEBT_PAYMENT]
    on_time = [m for m in debt_pays if not m.debt_id or m.occurred_at.day <= (db.get(M.Debt, m.debt_id).due_day + 2)]

    detail = [{"id": m.id, "date": m.occurred_at.isoformat(), "type": KIND_LABEL[m.kind], "direction": "Ingreso" if is_in(m) else "Egreso",
               "description": (f"{m.quantity} {m.product.name}" if m.product and m.quantity else (m.category or m.description or "")),
               "counterpart": links[m.id].payer, "operation_code": links[m.id].operation_code,
               "amount_cents": m.paid_cents, "demo": links[m.id].demo}
              for m in sorted(verified, key=lambda x: x.occurred_at)]
    consent = db.scalars(select(M.ReportConsent).where(M.ReportConsent.business_id == b.id).order_by(M.ReportConsent.month.desc())).all()
    total_in = sum(m.paid_cents for m in verified if is_in(m))
    total_out = sum(m.paid_cents for m in verified if not is_in(m))
    return {
        "business": {"id": b.id, "name": b.name, "owner_name": b.owner_name, "kind": b.kind, "description": b.description, "demo": b.demo},
        "generated_at": now_lima().isoformat(), "period": {"start": start.isoformat(), "end": end.isoformat()},
        "demo_data": b.demo or any(links[m.id].demo for m in verified),
        "rule": "Solo se incluyen ingresos y egresos hechos por Yape y verificados con el registro de Yape. El efectivo no se incluye.",
        "totals": {"income_cents": total_in, "out_cents": total_out, "net_cents": total_in - total_out,
                   "operations": len(verified), "income_operations": sum(1 for m in verified if is_in(m))},
        "months": rows,
        "capacity": {"months_used": len(used), "avg_income_cents": round(statistics.mean(incs)) if incs else None,
                     "avg_net_cents": avg_net, "worst_net_cents": worst, "suggested_max_installment_cents": suggested,
                     "current_installments_cents": sum(d.installment_cents for d in debts),
                     "rule": "Hasta 40% del saldo neto mensual promedio por Yape, sin pasar el 70% del peor mes."},
        "stability": {"weekly": weeks, "cv": round(cv, 2) if cv is not None else None,
                      "label": None if cv is None else ("Ingresos parejos" if cv < 0.2 else "Variación moderada" if cv < 0.4 else "Ingresos a saltos"),
                      "min_week_cents": min(winc) if winc else None, "max_week_cents": max(winc) if winc else None},
        "constancy": {"active_days": active, "period_days": period_days,
                      "active_days_pct": round(100 * active / period_days) if period_days else None,
                      "months_with_verified": len(months_all), "consecutive_months": consecutive},
        "clients": {"distinct_payers": len(payers), "top_payer_share_pct": round(100 * max(payers.values()) / tot_in) if tot_in else None},
        "discipline": {"debt_payments": len(debt_pays), "debt_on_time": len(on_time),
                       "personal_out_cents": sum(m.paid_cents for m in verified if m.kind == M.WITHDRAWAL),
                       "separates_home_business": any(m.kind == M.WITHDRAWAL for m in metrics.movements(db, b.id, s_dt, e_dt))},
        "verification": {"verified": len(verified), "pending": len(pending),
                         "verified_pct": round(100 * len(verified) / len(yape_mvs)) if yape_mvs else None},
        "movements": detail,
        "consents": [{"month": c.month, "decision": c.decision, "decided_at": c.decided_at.isoformat()} for c in consent],
        "disclaimer": ("Informe generado con los movimientos por Yape de la emprendedora, verificados con su registro de Yape. "
                       "Es un insumo para una evaluación futura: no es una calificación crediticia ni una aprobación de préstamo."),
    }
