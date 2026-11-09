"""Cruces de coherencia: stock esperado vs conteo y efectivo esperado vs conteo."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import ledger
from . import models as M
from .money import soles
from .textutil import pluralize
from .timeutil import now_lima


def stock_count(db: Session, business: M.Business, product: M.Product, counted: int, *, demo: bool = False,
                when=None, commit: bool = True) -> M.Count:
    expected = ledger.expected_stock(db, product)
    if expected is None:
        result, diff = "sin_datos", None
    else:
        diff = counted - expected
        result = "consistente" if diff == 0 else "diferencia"
    c = M.Count(business_id=business.id, kind="stock", product_id=product.id, counted=counted, expected=expected,
                difference=diff, result=result, demo=demo, counted_at=when or now_lima(),
                review_status="revisado" if result == "consistente" else "abierto")
    db.add(c)
    if commit:
        db.commit()
    return c


def cash_count(db: Session, business: M.Business, pocket: str, counted_cents: int, *, demo: bool = False,
               when=None, commit: bool = True) -> M.Count:
    known = ledger.opening_known(db, business.id)[pocket]
    bal = ledger.pocket_balances(db, business.id)[pocket]
    if not known:
        result, expected, diff = "sin_datos", None, None
    else:
        expected = bal
        diff = counted_cents - expected
        result = "consistente" if abs(diff) < 100 else "diferencia"
    c = M.Count(business_id=business.id, kind="caja", pocket=pocket, counted=counted_cents, expected=expected,
                difference=diff, result=result, demo=demo, counted_at=when or now_lima(),
                review_status="revisado" if result == "consistente" else "abierto")
    db.add(c)
    if commit:
        db.commit()
    return c


def stock_review_hints(db: Session, product: M.Product, diff: int) -> list[str]:
    hints = []
    if diff < 0:
        hints += [f"¿Hubo ventas de {product.name.lower()} que no registraste?",
                  "¿Alguna merma, regalo o prenda dañada?",
                  "¿Se registró bien la cantidad de la última compra?"]
    else:
        hints += ["¿Registraste una venta que al final no se hizo?",
                  "¿Llegó una compra que no registraste en unidades?",
                  "¿Hubo una devolución de un cliente?"]
    return hints


def cash_review_hints(diff: int) -> list[str]:
    if diff < 0:
        return ["¿Sacaste plata para la casa sin registrarlo?", "¿Pagaste algún gasto en efectivo que falta?",
                "¿Diste vuelto de más?"]
    return ["¿Te pagaron un fiado que no registraste?", "¿Pusiste plata tuya en la caja?",
            "¿Hay una venta en efectivo sin registrar?"]


def count_text(db: Session, c: M.Count) -> str:
    if c.kind == "stock":
        p = db.get(M.Product, c.product_id)
        name = pluralize(p.name.lower()) if c.counted != 1 else p.name.lower()
        if c.result == "sin_datos":
            return (f"Anoté que tienes {c.counted} {name}. Información incompleta: no tengo tu stock inicial, "
                    f"así que lo tomo como punto de partida desde ahora.")
        if c.result == "consistente":
            return f"Cuadra: contaste {c.counted} {name} y yo esperaba {c.expected}. ¡Todo en orden!"
        d = abs(c.difference)
        falt = "faltan" if c.difference < 0 else "sobran"
        return (f"Contaste {c.counted} {name} y yo esperaba {c.expected}: {falt} {d}. "
                f"Revisa: {stock_review_hints(db, p, c.difference)[0]} Puedes ajustarlo o dejarlo pendiente.")
    if c.result == "sin_datos":
        return (f"Anoté {soles(c.counted)} en {c.pocket}. Información incompleta: no tengo tu saldo inicial. "
                f"¿Quieres que lo use como saldo inicial? Di «empiezo con {c.counted // 100} en {c.pocket}».")
    if c.result == "consistente":
        return f"Cuadra: contaste {soles(c.counted)} en {c.pocket} y eso esperaba. ¡Bien!"
    falt = "faltan" if c.difference < 0 else "sobran"
    return (f"Contaste {soles(c.counted)} en {c.pocket} y yo esperaba {soles(c.expected)}: {falt} "
            f"{soles(abs(c.difference))}. {cash_review_hints(c.difference)[0]} Puedes dejarlo pendiente.")


def resolve_count(db: Session, business: M.Business, c: M.Count, action: str, note: str | None = None) -> M.Count:
    """action: ajustar | pendiente | revisado."""
    if action == "ajustar" and c.kind == "stock" and c.difference:
        p = db.get(M.Product, c.product_id)
        ledger.record(db, business, {"kind": M.STOCK_ADJ, "product_id": p.id, "quantity": c.difference,
                                     "reason": "ajuste", "description": f"Ajuste por conteo #{c.id}"},
                      op_id=f"ajuste-conteo-{c.id}", channel="app", commit=False)
        c.review_status = "ajustado"
    elif action == "ajustar" and c.kind == "stock" and c.result == "sin_datos":
        p = db.get(M.Product, c.product_id)
        p.initial_stock = c.counted - ledger.stock_delta(db, p.id)
        c.review_status = "ajustado"
    elif action == "pendiente":
        c.review_status = "pendiente"
    else:
        c.review_status = "revisado"
    if note:
        c.note = note
    db.commit()
    return c


def sale_check(db: Session, mv: M.Movement) -> str:
    """Resultado del cruce para una venta: consistente | diferencia | sin_datos."""
    if mv.kind not in (M.SALE, M.PURCHASE) or not mv.product_id:
        return "sin_datos"
    p = mv.product
    if not p or not p.track_stock or p.initial_stock is None:
        return "sin_datos"
    c = db.scalar(select(M.Count).where(M.Count.product_id == mv.product_id, M.Count.kind == "stock",
                                        M.Count.counted_at >= mv.occurred_at).order_by(M.Count.counted_at))
    if not c:
        return "sin_datos"
    if c.result == "consistente" or c.review_status == "ajustado":
        return "consistente" if c.result == "consistente" else "diferencia"
    return c.result


def summary(db: Session, business: M.Business) -> dict[str, Any]:
    counts = db.scalars(select(M.Count).where(M.Count.business_id == business.id)
                        .order_by(M.Count.counted_at.desc())).all()
    from .metrics import _count_dict
    items = []
    for c in counts:
        d = _count_dict(c)
        if c.product_id:
            p = db.get(M.Product, c.product_id)
            d["product"] = p.name
            if c.difference:
                d["hints"] = stock_review_hints(db, p, c.difference)
        elif c.difference:
            d["hints"] = cash_review_hints(c.difference)
        d["text"] = count_text(db, c)
        items.append(d)
    return {"counts": items,
            "open": [i for i in items if i["result"] != "consistente" and i["review_status"] in ("abierto", "pendiente")]}


def new_op() -> str:
    return uuid.uuid4().hex
