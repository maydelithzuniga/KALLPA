"""Unidades de venta y compra a partir de la ficha JSON del producto.

Ficha (Product.spec), por ejemplo para el tomate:
{
  "base": "kg",                                        # unidad en la que se lleva el stock
  "vende_por": [{"unidad": "kg", "precio_cents": 400}, {"unidad": "soles"}],
  "compra_por": {"unidad": "jaba", "equivale": 20, "costo_cents": 5000},   # 1 jaba = 20 kg, cuesta S/ 50
  "stock_inicial": {"cantidad": 2, "unidad": "jaba", "en_base": 40}
}
"""
from __future__ import annotations

from typing import Any

from .money import soles

PACK_DEFAULTS = {"docena": 12, "media docena": 6, "ciento": 100}
UNIT_NAMES = {"kg": ("kilo", "kilos"), "unidad": ("unidad", "unidades"), "atado": ("atado", "atados"), "jaba": ("jaba", "jabas"),
              "saco": ("saco", "sacos"), "caja": ("caja", "cajas"), "bolsa": ("bolsa", "bolsas"), "docena": ("docena", "docenas"),
              "paquete": ("paquete", "paquetes"), "soles": ("montoncito", "montoncitos"), "plato": ("plato", "platos")}


def base_unit(p) -> str:
    spec = getattr(p, "spec", None) or {}
    return spec.get("base") or getattr(p, "unit", None) or "unidad"


def unit_name(unit: str | None, n: float = 1) -> str:
    one, many = UNIT_NAMES.get(unit or "unidad", (unit or "unidad", (unit or "unidad") + "s"))
    return one if n is not None and n <= 1 else many


def equivalence(p, unit: str | None) -> float | None:
    """Cuántas unidades base trae `unit` (1 jaba = 20 kg)."""
    if unit is None:
        return None
    base = base_unit(p)
    if unit == base:
        return 1.0
    spec = getattr(p, "spec", None) or {}
    for key in ("compra_por",):
        c = spec.get(key) or {}
        if c.get("unidad") == unit and c.get("equivale"):
            return float(c["equivale"])
    for v in spec.get("vende_por", []) or []:
        if v.get("unidad") == unit and v.get("equivale"):
            return float(v["equivale"])
    if unit in PACK_DEFAULTS and base == "unidad":
        return float(PACK_DEFAULTS[unit])
    return None


def to_base(p, qty: float | None, unit: str | None) -> float | None:
    if qty is None:
        return None
    if unit in (None, "unidad") and base_unit(p) == "unidad":
        return float(qty)
    eq = equivalence(p, unit or base_unit(p))
    return float(qty) * eq if eq else None


def sell_price(p, unit: str | None) -> int | None:
    spec = getattr(p, "spec", None) or {}
    for v in spec.get("vende_por", []) or []:
        if v.get("unidad") == unit and v.get("precio_cents"):
            return int(v["precio_cents"])
    return None


def price_for(p, measure: float | None, unit: str | None) -> int | None:
    """Precio de lo vendido: precio de esa unidad, o precio por unidad base × equivalencia."""
    if not measure:
        return None
    own = sell_price(p, unit)
    if own:
        return round(own * measure)
    base_price = sell_price(p, base_unit(p)) or getattr(p, "price_cents", None)
    qty = to_base(p, measure, unit or base_unit(p))
    if base_price and qty is not None:
        return round(base_price * qty)
    return None


def base_qty(mv) -> float | None:
    """Cantidad vendida/comprada en unidad base. Si se vendió «3 soles de tomate», se estima con el precio por kilo."""
    p = mv.product
    if p is None:
        return None
    if mv.quantity:
        return float(mv.quantity) if base_unit(p) == "unidad" or not mv.measure_unit else to_base(p, mv.quantity, mv.measure_unit)
    if mv.measure:
        return to_base(p, mv.measure, mv.measure_unit or base_unit(p))
    if mv.kind == "venta" and mv.amount_cents:
        price = sell_price(p, base_unit(p)) or p.price_cents
        if price and base_unit(p) != "soles":
            return mv.amount_cents / price
    return None


def fmt_qty(x: float | None) -> str:
    if x is None:
        return "—"
    x = round(float(x), 2)
    if x.is_integer():
        return str(int(x))
    frac = {0.25: "¼", 0.5: "½", 0.75: "¾"}
    if x in frac:
        return frac[x]
    return f"{x:g}"


def describe_spec(p) -> dict[str, Any]:
    spec = getattr(p, "spec", None) or {}
    base = base_unit(p)
    vende = [("de a sol" if v.get("unidad") == "soles" else f"por {unit_name(v.get('unidad'))}") + (f" a {soles(v['precio_cents'], True)}" if v.get("precio_cents") else "")
             for v in spec.get("vende_por", []) or []]
    c = spec.get("compra_por") or {}
    compra = None
    if c.get("unidad"):
        compra = f"por {unit_name(c['unidad'])}" + (f" de {fmt_qty(c['equivale'])} {unit_name(base, c['equivale'])}" if c.get("equivale") and c["unidad"] != base else "") \
            + (f" a {soles(c['costo_cents'], True)}" if c.get("costo_cents") else "")
    return {"vende": ", ".join(vende) or None, "compra": compra, "base": base}
