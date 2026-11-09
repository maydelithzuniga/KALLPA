"""Resúmenes automáticos y alertas, agrupados para no saturar: como máximo 2 mensajes al día.

- Mañana (desde las 6 a. m.): alertas urgentes agrupadas (pago cercano, stock bajo, fiado viejo, costo que subió,
  meta atrasada). El día 1 del mes va con el resumen del mes.
- Noche (desde las 7 p. m.): resumen del día; el domingo, el de la semana. Si no registró nada, un recordatorio suave.
Se envían por WhatsApp cuando está conectado y siempre quedan en el chat de la app.
"""
from __future__ import annotations

import statistics
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import ledger, metrics, report, units
from . import models as M
from .money import soles
from .timeutil import DIAS, add_months, month_label, month_start, now_lima, today_lima

ALERT_REPEAT_DAYS = 3


def _day_profit_avg(db: Session, b: M.Business, today: date, days: int = 28) -> int | None:
    vals = []
    for i in range(1, days + 1):
        d = today - timedelta(days=i)
        st = metrics.day_stats(db, b, d)
        if st["active_days"]:
            vals.append(st["profit_cents"])
    return round(statistics.mean(vals)) if vals else None


def _main_goal(db: Session, b: M.Business) -> dict[str, Any] | None:
    gs = [g for g in metrics.goals(db, b) if g["kind"] == "ahorro" and g["status"] == "activa"]
    return gs[0] if gs else None


def _stock_low(db: Session, b: M.Business) -> list[dict[str, Any]]:
    out = []
    for i in metrics.inventory(db, b):
        if i["track_stock"] and i["expected_stock"] is not None and i["daily_avg"] and (i["days_left"] is not None and i["days_left"] <= 1):
            out.append(i)
    return out


def _stock_txt(i: dict[str, Any]) -> str:
    u = i["unit"]
    qty = f"{units.fmt_qty(max(0, i['expected_stock']))} {'kg' if u == 'kg' else units.unit_name(u, i['expected_stock'])}"
    when = "hoy" if (i["days_left"] or 0) < 1 else "1 día"
    return f"Te quedan {qty} de {i['name'].lower()}, te alcanza para {when}."


def overdue_receivables(db: Session, b: M.Business, min_days: int = 0) -> list[dict[str, Any]]:
    """Quién le debe a la emprendedora (agrupado por persona), del más antiguo al más nuevo."""
    today = today_lima()
    by: dict[str, dict[str, Any]] = {}
    for r in ledger.receivables(db, b.id):
        days = (today - datetime.fromisoformat(r["occurred_at"]).date()).days
        k = r["counterparty"]
        if k not in by:
            by[k] = {**r, "days": days, "sales": 1}
        else:
            by[k]["pending_cents"] += r["pending_cents"]
            by[k]["days"] = max(by[k]["days"], days)
            by[k]["sales"] += 1
    return sorted([x for x in by.values() if x["days"] >= min_days], key=lambda x: -x["days"])


def cobrar_text(db: Session, b: M.Business) -> str:
    """Lista de cobros para la vendedora: «Por cobrar (S/ 42): Doña Rosa S/ 30, hace 18 días; …»."""
    od = overdue_receivables(db, b, 0)
    if not od:
        return ""
    total = sum(r["pending_cents"] for r in od)
    when = lambda d: "de hoy" if d == 0 else ("de ayer" if d == 1 else f"hace {d} días")
    items = "; ".join(f"{r['counterparty']} {soles(r['pending_cents'])}, {when(r['days'])}" for r in od[:8])
    more = f" y {len(od) - 8} más" if len(od) > 8 else ""
    return f"Por cobrar ({soles(total)}): {items}{more}."


def alerts(db: Session, b: M.Business, today: date | None = None) -> list[dict[str, Any]]:
    """Alertas que valen la pena hoy. Cada una con una clave para no repetirla."""
    today = today or today_lima()
    out: list[dict[str, Any]] = []
    cash = metrics.cash_position(db, b)
    for u in cash["upcoming_payments"]:
        due = date.fromisoformat(u["due"])
        if due <= today + timedelta(days=1):
            when = "Hoy" if due == today else "Mañana"
            out.append({"key": f"pago:{u['name']}:{u['due']}", "icon": "📅", "text": f"{when} toca {u['name'].lower()}, {soles(u['amount_cents'])}."})
    for i in _stock_low(db, b):
        out.append({"key": f"stock:{i['id']}", "icon": "📦", "text": _stock_txt(i)})
    for a in metrics.cost_alerts(db, b, today):
        if a["pct"] >= 8:
            out.append({"key": f"costo:{a['product']}:{a['new_cost_cents']}", "icon": "📈",
                        "text": f"En el mayorista, {a['product'].lower()} te salió {a['pct']}% más caro que la semana pasada."})
    g = _main_goal(db, b)
    if g and g.get("behind"):
        out.append({"key": f"meta:{g['id']}", "icon": "🎯",
                    "text": f"Vas atrasada con «{g['name']}»: separa {soles(g.get('per_week_cents'))} esta semana para ponerte al día."})
    return out


# ------------------------------------------------------------------ resúmenes con enfoque distinto

def daily_text(db: Session, b: M.Business, d: date | None = None) -> str:
    """Cómo te fue hoy."""
    d = d or today_lima()
    st = metrics.day_stats(db, b, d)
    if not st["active_days"]:
        return "Hoy no anotaste nada. Si vendiste, mándame un audio o di «cerrar mi día» para cuadrar tu plata."
    avg = _day_profit_avg(db, b, d)
    comp = ""
    if avg:
        if st["profit_cents"] > avg * 1.1:
            comp = ", más que tu promedio"
        elif st["profit_cents"] < avg * 0.9:
            comp = f", menos que tu promedio ({soles(avg)})"
        else:
            comp = ", como un día normal"
    parts = [f"Hoy vendiste {soles(st['sales_cents'])} y ganaste {soles(st['profit_cents'])}{comp}."]
    if st["loss_cents"]:
        parts.append(f"Perdiste {soles(st['loss_cents'])} en mercadería o cosas malogradas.")
    g = _main_goal(db, b)
    if g and g.get("progress_pct") is not None:
        parts.append(f"Vas al {g['progress_pct']}% de tu {g['name'].lower()}.")
    low = _stock_low(db, b)
    if low:
        i = low[0]
        parts.append(f"Mañana compra más {i['name'].lower()}: te queda para {'hoy' if (i['days_left'] or 0) < 1 else '1 día'}.")
    c = cobrar_text(db, b)
    return " ".join(parts) + (f"\n{c}" if c else "")


def weekly_text(db: Session, b: M.Business, d: date | None = None) -> str:
    """Qué aprendiste de tu semana."""
    d = d or today_lima()
    ws = d - timedelta(days=6)
    cur = metrics.period_stats(db, b, ws, d + timedelta(days=1))
    prev = metrics.period_stats(db, b, ws - timedelta(days=7), ws)
    diff = cur["profit_cents"] - prev["profit_cents"]
    parts = [f"Esta semana ganaste {soles(cur['profit_cents'])}"
             + (f", {soles(abs(diff))} {'más' if diff >= 0 else 'menos'} que la anterior." if prev["active_days"] else ".")]
    ms = [m for m in metrics.product_margins(db, b, ws, d + timedelta(days=1)) if m["margin_cents"] is not None]
    if len(ms) >= 2:
        best = max(ms, key=lambda m: m["margin_cents"])
        most = max(ms, key=lambda m: m["revenue_cents"])
        if best["product_id"] != most["product_id"]:
            parts.append(f"Lo que más vendiste fue {most['name'].lower()}, pero lo que más te dejó fue {best['name'].lower()}.")
        else:
            other = sorted(ms, key=lambda m: -m["margin_cents"])[1]
            parts.append(f"El {best['name'].lower()} te dejó más que el {other['name'].lower()}.")
    wp = metrics.weekday_pattern(db, b)
    if wp["available"] and wp["worst"]["vs_avg_pct"] <= -20:
        prev_day = DIAS[(wp["worst"]["weekday"] - 1) % 7]
        parts.append(f"Los {wp['worst']['name']} vendes poco: compra menos el {prev_day}.")
    if cur["loss_cents"]:
        top = _top_loss(db, b, ws, d)
        parts.append(f"Se te malogró {soles(cur['loss_cents'])}" + (f", sobre todo {top}." if top else "."))
    c = cobrar_text(db, b)
    return " ".join(parts) + (f"\n{c}" if c else "")


def _top_loss(db: Session, b: M.Business, start: date, end: date) -> str | None:
    s, e = datetime(start.year, start.month, start.day), datetime(end.year, end.month, end.day) + timedelta(days=1)
    by: dict[str, int] = {}
    for m in metrics.movements(db, b.id, s, e, kinds={M.LOSS}):
        name = (m.product.name.lower() if m.product else (m.description or "otros"))
        by[name] = by.get(name, 0) + m.amount_cents
    if not by:
        return None
    name, amt = max(by.items(), key=lambda x: x[1])
    return f"{name} ({soles(amt)})"


def monthly_text(db: Session, b: M.Business, d: date | None = None) -> str:
    """Cómo has crecido (se envía el día 1 sobre el mes que terminó)."""
    d = d or today_lima()
    m0 = add_months(month_start(d), -1)
    m1 = add_months(m0, -1)
    cur = metrics.period_stats(db, b, m0, month_start(d))
    prev = metrics.period_stats(db, b, m1, m0)
    parts = [f"En {month_label(m0).split()[0]} ganaste {soles(cur['profit_cents'])}"]
    if prev["profit_cents"] > 0:
        pct = round(100 * (cur["profit_cents"] - prev["profit_cents"]) / prev["profit_cents"])
        parts[0] += f", un {abs(pct)}% {'más' if pct >= 0 else 'menos'} que en {month_label(m1).split()[0]}."
    else:
        parts[0] += "."
    if cur["goal_savings_cents"]:
        parts.append(f"Separaste {soles(cur['goal_savings_cents'])} para tu meta.")
    if cur["withdrawals_cents"]:
        parts.append(f"Para la casa sacaste {soles(cur['withdrawals_cents'])}.")
    rep = report.build_bcp(db, b, add_months(m0, -2), month_start(d) - timedelta(days=1))
    parts.append("Tu informe para el BCP está listo: ¿lo envío?")
    cuota = rep["capacity"].get("suggested_max_installment_cents")
    if cuota:
        parts.append(f"Con tus ingresos por Yape podrías pagar una cuota de hasta {soles(cuota)} al mes.")
    c = cobrar_text(db, b)
    return " ".join(parts) + (f"\n{c}" if c else "")


# ------------------------------------------------------------------ envío

def _recent_alert_keys(db: Session, b: M.Business, today: date) -> set[str]:
    since = datetime(today.year, today.month, today.day) - timedelta(days=ALERT_REPEAT_DAYS)
    keys: set[str] = set()
    for n in db.scalars(select(M.Notification).where(M.Notification.business_id == b.id, M.Notification.created_at >= since)).all():
        keys.update(n.alert_keys or [])
    return keys


def _deliver(db: Session, b: M.Business, key: str, kind: str, text: str, alert_keys: list[str]) -> M.Notification | None:
    if db.scalar(select(M.Notification).where(M.Notification.business_id == b.id, M.Notification.key == key)):
        return None
    n = M.Notification(business_id=b.id, key=key, kind=kind, text=text, alert_keys=alert_keys)
    from .config import settings
    if settings.whatsapp_available and b.phone:
        import os
        from . import whatsapp
        tpl = os.getenv("WHATSAPP_TEMPLATE_RESUMEN", "")
        if tpl:   # Meta exige plantilla aprobada para escribirle primero (fuera de las 24 h)
            n.sent_whatsapp = whatsapp.send_template(b.phone, tpl, [text.replace("\n", " · ")])
        else:
            whatsapp.send_text(b.phone, text)
            n.sent_whatsapp = True
    db.add(n)
    db.add(M.ChatLog(business_id=b.id, role="bot", text=text, channel="aviso"))
    db.commit()
    return n


def _alerts_block(db: Session, b: M.Business, today: date, limit: int = 3) -> tuple[list[str], list[str]]:
    seen = _recent_alert_keys(db, b, today)
    fresh = [a for a in alerts(db, b, today) if a["key"] not in seen][:limit]
    return [f"{a['icon']} {a['text']}" for a in fresh], [a["key"] for a in fresh]


def run(db: Session, b: M.Business, now: datetime | None = None, force: str | None = None) -> list[M.Notification]:
    """Genera los mensajes que tocan ahora. `force`: manana | noche | semana | mes (para probar en la demo)."""
    if b.setup_state != "listo":
        return []
    now = now or now_lima()
    today = now.date()
    created: list[M.Notification] = []
    hello = f"Buenos días{', ' + b.owner_name if b.owner_name else ''}."
    slot_morning = force in ("manana", "mes") or (force is None and now.hour >= 6)
    slot_night = force in ("noche", "semana") or (force is None and now.hour >= 19)
    suffix = f":{force}:{now_lima().strftime('%H%M%S%f')}" if force else ""
    if slot_morning:
        lines, keys = _alerts_block(db, b, today)
        if force == "mes" or (force is None and today.day == 1):
            text = f"{hello} Tu mes en resumen: {monthly_text(db, b, today)}" + (("\n\nPara hoy:\n" + "\n".join(lines)) if lines else "")
            n = _deliver(db, b, f"{today}:manana{suffix}", "mes", text, keys)
            if n:
                _consent_draft(db, b)
        elif lines:
            n = _deliver(db, b, f"{today}:manana{suffix}", "manana", f"{hello} Para hoy:\n" + "\n".join(lines), keys)
        else:
            n = None
        if n:
            created.append(n)
    if slot_night:
        if force == "semana" or (force is None and today.weekday() == 6):
            text = "Tu semana: " + weekly_text(db, b, today)
            kind = "semana"
        else:
            text = daily_text(db, b, today)
            kind = "noche"
        n = _deliver(db, b, f"{today}:noche{suffix}", kind, text, [])
        if n:
            created.append(n)
    return created


def mark_night_sent(db: Session, b: M.Business, text: str) -> None:
    """El cierre del día ya hizo el resumen de la noche: no se repite."""
    today = today_lima()
    key = f"{today}:noche"
    if not db.scalar(select(M.Notification).where(M.Notification.business_id == b.id, M.Notification.key == key)):
        db.add(M.Notification(business_id=b.id, key=key, kind="cierre", text=text, alert_keys=[]))
        db.commit()


def _consent_draft(db: Session, b: M.Business) -> None:
    """Para que un «sí» responda la pregunta del informe BCP en el chat o en WhatsApp."""
    import uuid
    prev = add_months(month_start(today_lima()), -1).strftime("%Y-%m")
    if db.scalar(select(M.ReportConsent).where(M.ReportConsent.business_id == b.id, M.ReportConsent.month == prev)):
        return
    convs = [f"web:{b.id}", f"whatsapp:{b.phone or 'app-' + str(b.id)}"]
    for conv in convs:
        for d in db.scalars(select(M.Draft).where(M.Draft.business_id == b.id, M.Draft.conversation == conv, M.Draft.status == "abierto")).all():
            d.status = "cancelado"
        db.add(M.Draft(business_id=b.id, conversation=conv, op_id=uuid.uuid4().hex, action="consentimiento",
                       data={"month": prev}, summary_read=True))
    db.commit()


def latest(db: Session, b: M.Business, limit: int = 5) -> list[dict[str, Any]]:
    rows = db.scalars(select(M.Notification).where(M.Notification.business_id == b.id, M.Notification.kind != "cierre")
                      .order_by(M.Notification.id.desc()).limit(limit)).all()
    label = {"manana": "Aviso de la mañana", "noche": "Resumen de tu día", "semana": "Resumen de tu semana", "mes": "Resumen de tu mes"}
    return [{"id": n.id, "kind": n.kind, "title": label.get(n.kind, "Mensaje"), "text": n.text, "created_at": n.created_at.isoformat(),
             "sent_whatsapp": n.sent_whatsapp} for n in rows]


def enrich(db: Session, b: M.Business, data: dict[str, Any]) -> dict[str, Any]:
    """Agrega al panel: mensajes automáticos, alertas de hoy, semana en palabras y fiados con mensaje listo."""
    from .config import settings
    if settings.notify_auto:
        run(db, b)
    data["alerts_today"] = alerts(db, b)
    data["week_text"] = weekly_text(db, b)
    data["receivables"] = overdue_receivables(db, b, 0)
    data["cobrar_text"] = cobrar_text(db, b)
    data["messages"] = latest(db, b)
    return data
