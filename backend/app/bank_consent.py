"""Cada fin de mes Kallpa pregunta si la emprendedora quiere enviar su informe de finanzas a los bancos aliados.

- El último día del mes pregunta por el mes que termina; desde el día 1, por el mes anterior si aún no respondió.
- Pregunta sí o sí: al cerrar el día, en el aviso de la noche y, si no responde, una vez al día hasta que decida.
- Nunca se envía sin su «sí» (autorización por mes). En esta demo el envío es simulado.
"""
from __future__ import annotations

import calendar
import os
from datetime import date, datetime

from sqlalchemy import select

from . import models as M
from .timeutil import add_months, month_label, month_start


def banks() -> str:
    raw = os.getenv("PARTNER_BANKS", "BCP")
    names = [x.strip() for x in raw.split(",") if x.strip()] or ["BCP"]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " y " + names[-1]


def is_last_day(d: date) -> bool:
    return d.day == calendar.monthrange(d.year, d.month)[1]


def report_month(today: date) -> date:
    """Mes del informe: el que termina hoy (último día) o el anterior (desde el día 1)."""
    return month_start(today) if is_last_day(today) else add_months(month_start(today), -1)


def pending_month(db, b: M.Business, today: date) -> date | None:
    """Mes cuyo informe aún no decidió. None si ya respondió o no hubo movimientos."""
    for m in ([month_start(today)] if is_last_day(today) else []) + [add_months(month_start(today), -1)]:
        key = m.strftime("%Y-%m")
        if db.scalar(select(M.ReportConsent).where(M.ReportConsent.business_id == b.id, M.ReportConsent.month == key)):
            continue
        end = add_months(m, 1)
        has = db.scalar(select(M.Movement.id).where(M.Movement.business_id == b.id, M.Movement.kind != M.OPENING,
                                                    M.Movement.occurred_at >= datetime(m.year, m.month, 1),
                                                    M.Movement.occurred_at < datetime(end.year, end.month, 1)))
        if has:
            return m
    return None


def question_text(m: date) -> str:
    return (f"📊 Tu informe de finanzas de {month_label(m)} está listo (solo lo verificado por Yape). "
            f"¿Quieres que lo enviemos a nuestros bancos aliados ({banks()}) para que conozcan tu negocio y puedan "
            "ofrecerte productos financieros, como créditos para capital de trabajo, ahorro o seguros? Tú decides cada mes.")


QUICK = ["Sí, envíalo", "No por ahora", "¿Qué se envía?"]


def what_is_sent() -> str:
    return (f"Se envía tu informe financiero en PDF a {banks()}: tus ingresos y egresos por Yape verificados por mes, "
            "tu flujo neto, cuánta cuota podrías pagar, qué tan estables son tus ventas y cuántos clientes tienes. "
            "No se envía tu efectivo ni tus conversaciones. Sirve para que el banco vea que tu negocio funciona y te ofrezca "
            "productos a tu medida. Es tu decisión: ¿lo enviamos?")


def asked_today(db, b: M.Business, conv: str, m: date, today: date) -> bool:
    for d in db.scalars(select(M.Draft).where(M.Draft.business_id == b.id, M.Draft.action == "consentimiento",
                                              M.Draft.conversation == conv)).all():
        if (d.data or {}).get("month") == m.strftime("%Y-%m") and (d.data or {}).get("asked_on") == today.isoformat():
            return True
    return False


def sent_text(db, b: M.Business, m: date) -> str:
    try:
        from .report_pdf import analyze
        code = analyze(db, b)["code"]
    except Exception:   # noqa: BLE001
        code = None
    return (f"✓ Listo. Enviamos tu informe de {month_label(m)} a {banks()} (en esta demo el envío es simulado)."
            + (f" Código de tu informe: {code}." if code else "")
            + " Te dejo tu copia. Si un banco tiene una oferta para ti, te aviso por aquí. El próximo mes te vuelvo a preguntar.")
