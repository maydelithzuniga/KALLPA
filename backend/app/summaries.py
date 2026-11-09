"""Textos cortos para el chat: como una amiga que sabe de números. Sin IA externa."""
from __future__ import annotations

import re

from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import ledger, metrics
from . import models as M
from .money import soles
from .timeutil import fmt_day, month_start, today_lima


def _methods(st) -> str:
    parts = []
    by = st["sales_by_method"]
    if by["yape"]:
        parts.append(f"{soles(by['yape'])} Yape")
    if by["efectivo"]:
        parts.append(f"{soles(by['efectivo'])} efectivo")
    if by["fiado"]:
        parts.append(f"{soles(by['fiado'])} fiado")
    return f" ({', '.join(parts)})" if parts else ""


def cash_line(db: Session, b: M.Business) -> str:
    cash = metrics.cash_position(db, b)
    if cash["complete"]:
        return f"En caja tienes {soles(cash['total_cents'])} disponibles ({soles(cash['efectivo_cents'])} efectivo, {soles(cash['yape_cents'])} Yape)."
    return (f"Desde que registras, entraron y salieron en neto {soles(cash['total_cents'])}. "
            f"Para decirte cuánto tienes, falta tu saldo inicial de {' y '.join(cash['missing'])}.")


def daily(db: Session, b: M.Business, d: date | None = None) -> str:
    d = d or today_lima()
    st = metrics.day_stats(db, b, d)
    gasto = st["business_outflow_cents"] - st["debt_payments_cents"]
    txt = f"Tu día, {fmt_day(d)}: vendiste {soles(st['sales_cents'])}{_methods(st)}."
    if st["collections_cents"]:
        txt += f" Te pagaron {soles(st['collections_cents'])} de fiados."
    txt += f" Gastaste {soles(gasto)} del negocio."
    txt += f" Ganancia del día: {soles(st['profit_cents'])}{' (aprox., falta algún costo)' if st['profit_estimated'] else ''}."
    if st["withdrawals_cents"]:
        txt += f" Sacaste {soles(st['withdrawals_cents'])} para la casa."
    if st.get("loss_cents"):
        txt += f" Tuviste pérdidas por {soles(st['loss_cents'])}."
    txt += " " + cash_line(db, b)
    gs = [g for g in metrics.goals(db, b) if g["status"] == "activa" and g.get("progress_pct") is not None]
    if gs:
        g = gs[-1] if gs[-1]["kind"] == "ahorro" else gs[0]
        txt += f" Vas al {g['progress_pct']}% de tu meta {('de ' + g['name'].lower()) if g['kind'] == 'ahorro' else 'de reposición'}."
    for a in metrics.cost_alerts(db, b, d):
        if a["pct"] > 0:
            txt += f" Ojo: {a['product'].lower()} subió {a['pct']}% vs la semana pasada."
            break
    return txt


def weekly(db: Session, b: M.Business) -> str:
    today = today_lima()
    ws = metrics.week_start(today)
    st = metrics.period_stats(db, b, ws, today + timedelta(days=1))
    txt = (f"Esta semana vendiste {soles(st['sales_cents'])}{_methods(st)}. Gastaste {soles(st['business_outflow_cents'])} "
           f"del negocio y ganaste {soles(st['profit_cents'])}.")
    if st["withdrawals_cents"]:
        txt += f" Para la casa sacaste {soles(st['withdrawals_cents'])}."
    wp = metrics.weekday_pattern(db, b)
    if wp["available"]:
        txt += f" Tu mejor día suele ser el {wp['best']['name']}."
    return txt + " " + cash_line(db, b)


def monthly(db: Session, b: M.Business) -> str:
    today = today_lima()
    st = metrics.period_stats(db, b, month_start(today), today + timedelta(days=1))
    tr = metrics.month_trend(db, b)
    txt = f"Este mes llevas {soles(st['sales_cents'])} en ventas y {soles(st['profit_cents'])} de ganancia."
    if tr["pct"] is not None:
        if tr["direction"] == "mejor":
            txt += f" Vas {tr['pct']}% mejor que el mes pasado a esta fecha. ¡Bien!"
        elif tr["direction"] == "peor":
            txt += f" Vas {abs(tr['pct'])}% abajo del mes pasado a esta fecha."
        else:
            txt += " Vas parecido al mes pasado."
    be = metrics.break_even(db, b)
    if be.get("available"):
        txt += f" Para no perder necesitas vender {soles(be['break_even_monthly_cents'])} al mes."
    return txt


def explain(db: Session, b: M.Business, topic: str) -> str:
    today = today_lima()
    st = metrics.period_stats(db, b, metrics.week_start(today), today + timedelta(days=1))
    rec = sum(r["pending_cents"] for r in ledger.receivables(db, b.id))
    if topic == "flujo":
        usable = st["collected_cents"] - st["business_outflow_cents"] - st["withdrawals_cents"]
        return (f"Es la plata que de verdad tienes en la mano para usar. Esta semana vendiste {soles(st['sales_cents'])}, "
                f"pero {soles(st['new_credit_cents'])} te los deben de fiado y pagaste {soles(st['business_outflow_cents'])} "
                f"en compras y gastos{(' y sacaste ' + soles(st['withdrawals_cents']) + ' para la casa') if st['withdrawals_cents'] else ''}. "
                f"Así que para usar te quedaron {soles(usable)}, no {soles(st['sales_cents'])}.")
    if topic == "ganancia":
        return (f"Es lo que te queda después de pagar lo que te costó lo que vendiste y los gastos del negocio. "
                f"Esta semana vendiste {soles(st['sales_cents'])}, la mercadería vendida te costó {soles(st['cogs_cents'])} "
                f"y gastaste {soles(st['business_expenses_total_cents'])}: ganaste {soles(st['profit_cents'])}.")
    if topic == "margen":
        ms = [m for m in metrics.product_margins(db, b, today - timedelta(days=30), today + timedelta(days=1)) if m["margin_per_unit_cents"] is not None]
        if ms:
            m = ms[0]
            return (f"Es cuánto te queda de cada venta después de pagar lo que te costó. Por ejemplo, {m['name'].lower()}: "
                    f"lo vendes en promedio a {soles(m['avg_price_cents'])} y te deja {soles(m['margin_per_unit_cents'])} por unidad "
                    f"({m['margin_pct']}%).")
        return "Es cuánto te queda de cada venta después de pagar lo que te costó. Dime el costo de tus productos para calcularlo."
    if topic == "equilibrio":
        be = metrics.break_even(db, b)
        intro = "Es lo mínimo que tienes que vender para no perder: lo que cubre tus gastos fijos del mes. "
        if not be.get("fixed_cents"):
            return (intro + "Aún no me dijiste tus gastos fijos (alquiler del puesto, luz, celular, ayudante). "
                    "Dímelos así: «pago 250 de alquiler al mes» y te digo cuánto tienes que vender cada día.")
        if be.get("available"):
            return (intro + f"Tus gastos fijos son {soles(be['fixed_cents'])} al mes y de cada sol que vendes te quedan "
                    f"{round(be['contribution_margin_pct'])} céntimos para cubrirlos. Necesitas vender {soles(be['break_even_monthly_cents'])} "
                    f"al mes, unos {soles(be['break_even_daily_cents'])} al día.")
        return intro + be.get("reason", "")
    if topic == "rotacion":
        r = metrics.rotation(db, b)
        first = db.scalar(select(func.min(M.Movement.occurred_at)).where(M.Movement.business_id == b.id))
        days = (today - first.date()).days + 1 if first else 0
        parts = ["Es qué tan rápido se convierte tu mercadería en plata."]
        if days < 7:
            inv = r.get("inventory_value_cents") or 0
            parts.append((f"Hoy tienes unos {soles(inv)} en mercadería (a lo que te costó). " if inv else "")
                         + "Con una semana de ventas registradas te digo en cuántos días la vendes y qué producto se mueve más lento.")
        else:
            if r["inventory_days"]:
                parts.append(f"Lo que tienes en mercadería lo vendes en unos {min(r['inventory_days'], 365)} días"
                             + (": se mueve rápido 👍." if r["inventory_days"] <= 15 else ". Si pasa de un mes, compra menos de lo que se vende lento."))
            if r["cash_days"]:
                parts.append(f"Con tu caja de hoy cubres unos {min(r['cash_days'], 365)} días de gastos.")
        return " ".join(parts)
    if topic == "caja":
        return "Es la plata que tienes hoy para usar, sumando efectivo y Yape. " + cash_line(db, b)
    if topic == "cuota":
        from .report import capacity
        cap = capacity(db, b)
        if cap["suggested_max_installment_cents"]:
            return (f"Según tus números, cada mes te sobran unos {soles(cap['avg_net_cents'])} después de gastos del negocio "
                    f"y de la casa. Una cuota cómoda sería hasta {soles(cap['suggested_max_installment_cents'])} al mes.")
        return "Aún no tengo suficientes meses registrados para decirte una cuota cómoda. Sigue registrando."
    return ""


def receivables_text(db: Session, b: M.Business) -> str:
    rec = ledger.receivables(db, b.id)
    if not rec:
        return "Nadie te debe. ¡Bien!"
    by: dict[str, int] = {}
    for r in rec:
        by[r["counterparty"]] = by.get(r["counterparty"], 0) + r["pending_cents"]
    total = sum(by.values())
    top = ", ".join(f"{k} {soles(v)}" for k, v in sorted(by.items(), key=lambda x: -x[1])[:4])
    return f"Te deben {soles(total)}: {top}."


def inventory_text(db: Session, b: M.Business, text: str = "") -> str:
    from . import nlu, units
    inv = [i for i in metrics.inventory(db, b) if i["track_stock"]]
    if not inv:
        return "No llevo stock de tus productos. Dime por ejemplo «tengo 10 kilos de papa» para empezar a contarlos."
    t = nlu.normalize(text or "")
    asked = [i for i in inv if any(re.search(rf"\b{re.escape(nlu.normalize(w))}", t) for w in [i["name"], *(i["aliases"] or [])] if w)]
    parts = []
    for i in (asked or inv)[:8]:
        exp = i["expected_stock"]
        if exp is None:
            parts.append(f"{i['name']}: sin stock inicial")
        else:
            line = f"{i['name']}: {units.fmt_qty(exp)} {units.unit_name(i['unit'], exp)}"
            if i.get("days_left") is not None and i["days_left"] <= 3:
                line += f" (te alcanza para unos {i['days_left']} días)"
            parts.append(line)
    return ("Según tus registros te queda: " if asked else "Según tus registros tienes: ") + "; ".join(parts) + "."


def goals_text(db: Session, b: M.Business) -> str:
    gs = [g for g in metrics.goals(db, b) if g["status"] == "activa"]
    if not gs:
        return "Aún no tienes metas. Dime por ejemplo «quiero juntar 1500 para una congeladora en diciembre»."
    return " ".join(g["message"] for g in gs[:2])


def help_text(db: Session, b: M.Business) -> str:
    """Ayuda con ejemplos de SUS productos (no siempre polos)."""
    prods = [p for p in db.query(M.Product).filter(M.Product.business_id == b.id).limit(3)]
    if prods:
        from . import units
        a = prods[0].name.lower()
        u = units.base_unit(prods[0])
        venta = f"vendí 2 kilos de {a} en efectivo" if u == "kg" else f"vendí 3 {a} por Yape"
        b2 = prods[1].name.lower() if len(prods) > 1 else a
        return (f"Puedes decirme cosas como: «{venta}», «gasté 5 en bolsas», «se malogró un kilo de {b2}», "
                f"«Rosa se llevó 2 kilos de {b2} fiado», «Rosa me pagó 5», «¿cuánto {a} me queda?», "
                "«resumen», «cuánto tengo», «a quién tengo que cobrar», «cerrar mi día» o «deshacer».")
    return HELP


HELP = ("Puedes decirme cosas como: «vendí 3 polos a 25 por Yape», «compré una docena de polos por 144», "
        "«pagué la luz 80», «me saqué 50 para la casa», «Rosa me pagó 20 del fiado», «tengo 17 polos», "
        "«resumen», «¿qué es el flujo de caja?» o «quiero ahorrar 1500 para diciembre».")
