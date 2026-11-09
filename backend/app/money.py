"""Importes en céntimos enteros y formato en soles."""
from __future__ import annotations


def to_cents(soles: float | int | str) -> int:
    return int(round(float(soles) * 100))


def soles(cents: int | None, decimals: bool | None = None) -> str:
    if cents is None:
        return "S/ —"
    neg = cents < 0
    cents = abs(int(cents))
    whole, frac = divmod(cents, 100)
    show_dec = decimals if decimals is not None else frac != 0
    txt = f"{whole:,}"
    if show_dec:
        txt += f".{frac:02d}"
    return f"{'-' if neg else ''}S/ {txt}"
