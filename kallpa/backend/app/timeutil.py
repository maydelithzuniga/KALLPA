"""Fechas en horario de Lima. Se guardan como datetime 'naive' en hora local de Lima."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

LIMA = ZoneInfo("America/Lima")

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]


def now_lima() -> datetime:
    return datetime.now(LIMA).replace(tzinfo=None, microsecond=0)


def today_lima() -> date:
    return now_lima().date()


def day_bounds(d: date) -> tuple[datetime, datetime]:
    start = datetime(d.year, d.month, d.day)
    return start, start + timedelta(days=1)


def month_start(d: date) -> date:
    return date(d.year, d.month, 1)


def add_months(d: date, n: int) -> date:
    m = d.month - 1 + n
    y = d.year + m // 12
    m = m % 12 + 1
    return date(y, m, 1)


def month_label(d: date) -> str:
    return f"{MESES[d.month - 1]} {d.year}"


def fmt_day(d: date) -> str:
    return f"{DIAS[d.weekday()]} {d.day}"
