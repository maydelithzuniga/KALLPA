"""Registro de movimientos: caja e inventario se actualizan juntos en una transacción.

Cada movimiento confirmado genera líneas de caja (CashEntry) y de stock (StockEntry).
El saldo de caja y el stock esperado se calculan sumando esas líneas: una sola fuente
de datos para chat, panel y reporte.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import models as M
from .timeutil import now_lima


class LedgerError(ValueError):
    pass


def compute_discount(qty: int | None, unit_price_ref: int | None, final_total: int) -> tuple[int | None, int | None]:
    """Descuento = max(0, total de referencia − precio final). Sin precio habitual: sin calcular."""
    if unit_price_ref is None or not qty:
        return None, None
    reference_total = unit_price_ref * qty
    return reference_total, max(0, reference_total - final_total)


def find_movement_by_op(db: Session, op_id: str) -> M.Movement | None:
    return db.scalar(select(M.Movement).where(M.Movement.op_id == op_id))


def record(db: Session, business: M.Business, data: dict[str, Any], *, op_id: str,
           source_message_id: str | None = None, channel: str = "web", demo: bool = False,
           commit: bool = True) -> tuple[M.Movement, bool]:
    """Registra un movimiento confirmado. Devuelve (movimiento, creado).

    Si el op_id ya existe no se duplica nada (reintentos / doble confirmación)."""
    existing = find_movement_by_op(db, op_id)
    if existing:
        return existing, False
    mv = M.Movement(business_id=business.id, op_id=op_id, source_message_id=source_message_id,
                    channel=channel, demo=demo)
    _fill(db, business, mv, data)
    db.add(mv)
    db.flush()
    _build_effects(db, business, mv)
    _post_effects(db, business, mv)
    if commit:
        db.commit()
    return mv, True


def _fill(db: Session, business: M.Business, mv: M.Movement, data: dict[str, Any]) -> None:
    kind = data["kind"]
    mv.kind = kind
    occurred = data.get("occurred_at")
    if isinstance(occurred, str):
        occurred = datetime.fromisoformat(occurred)
    mv.occurred_at = occurred or now_lima()
    mv.method = data.get("method")
    mv.to_method = data.get("to_method")
    mv.product_id = data.get("product_id")
    mv.quantity = data.get("quantity")
    mv.category = data.get("category")
    mv.expense_type = data.get("expense_type")
    mv.counterparty = data.get("counterparty")
    mv.description = data.get("description")
    mv.raw_text = data.get("raw_text")
    mv.parent_id = data.get("parent_id")
    mv.goal_id = data.get("goal_id")
    mv.debt_id = data.get("debt_id")
    mv.units_pending = bool(data.get("units_pending"))
    mv.origin = data.get("origin", "autodeclarado")
    product = db.get(M.Product, mv.product_id) if mv.product_id else None

    if kind == M.SALE:
        total = int(data["amount_cents"])
        mv.amount_cents = total
        paid = data.get("paid_cents")
        mv.paid_cents = total if paid is None else int(paid)
        if mv.paid_cents > total:
            raise LedgerError("Lo cobrado no puede ser mayor que el precio acordado")
        if mv.paid_cents > 0 and mv.method not in M.POCKETS:
            raise LedgerError("Falta el medio de pago")
        ref_price = data.get("unit_price_ref_cents")
        if ref_price is None and product is not None:
            ref_price = product.price_cents
        mv.unit_price_ref_cents = ref_price
        mv.reference_total_cents, mv.discount_cents = compute_discount(mv.quantity, ref_price, total)
        mv.unit_cost_cents = data.get("unit_cost_cents", product.cost_cents if product else None)
        mv.category = mv.category or "Venta de productos"
    elif kind == M.PURCHASE:
        total = int(data["amount_cents"])
        mv.amount_cents = total
        mv.paid_cents = total if data.get("paid_cents") is None else int(data["paid_cents"])
        if mv.paid_cents > 0 and mv.method not in M.POCKETS:
            raise LedgerError("Falta el medio de pago")
        if mv.quantity:
            mv.unit_cost_cents = round(total / mv.quantity)
        else:
            mv.units_pending = True if data.get("generic") or not mv.product_id else mv.units_pending
        mv.category = mv.category or "Compra de mercadería"
    elif kind in (M.EXPENSE, M.WITHDRAWAL, M.CONTRIBUTION, M.DEBT_PAYMENT, M.COLLECTION, M.OPENING, M.GOAL_SAVING):
        mv.amount_cents = int(data["amount_cents"])
        mv.paid_cents = mv.amount_cents
        if mv.method not in M.POCKETS:
            raise LedgerError("Falta el medio de pago")
        if kind == M.WITHDRAWAL:
            mv.category = mv.category or "Gastos de la casa"
    elif kind == M.TRANSFER:
        mv.amount_cents = int(data["amount_cents"])
        mv.paid_cents = mv.amount_cents
        if mv.method not in M.POCKETS or mv.to_method not in M.POCKETS or mv.method == mv.to_method:
            raise LedgerError("El traslado necesita origen y destino distintos")
    elif kind == M.STOCK_ADJ:
        mv.amount_cents = int(data.get("amount_cents") or 0)
        mv.paid_cents = mv.amount_cents
        mv.category = data.get("reason", "ajuste")
        if not mv.product_id or mv.quantity is None:
            raise LedgerError("El ajuste necesita producto y cantidad")
        if mv.amount_cents and mv.method not in M.POCKETS:
            raise LedgerError("Falta el medio de pago")
    else:
        raise LedgerError(f"Tipo de movimiento desconocido: {kind}")


def _cash(db, mv, pocket, delta):
    if delta:
        db.add(M.CashEntry(business_id=mv.business_id, movement_id=mv.id, pocket=pocket,
                           delta_cents=delta, occurred_at=mv.occurred_at))


def _stock(db, mv, product_id, delta, reason):
    if delta:
        db.add(M.StockEntry(business_id=mv.business_id, movement_id=mv.id, product_id=product_id,
                            delta_qty=delta, reason=reason, occurred_at=mv.occurred_at))


def _build_effects(db: Session, business: M.Business, mv: M.Movement) -> None:
    product = db.get(M.Product, mv.product_id) if mv.product_id else None
    k = mv.kind
    if k == M.SALE:
        _cash(db, mv, mv.method, mv.paid_cents)
        if product and product.track_stock and mv.quantity:
            _stock(db, mv, product.id, -mv.quantity, "venta")
    elif k == M.PURCHASE:
        _cash(db, mv, mv.method, -mv.paid_cents)
        if product and product.track_stock and mv.quantity:
            _stock(db, mv, product.id, mv.quantity, "compra")
    elif k in (M.EXPENSE, M.WITHDRAWAL, M.DEBT_PAYMENT):
        _cash(db, mv, mv.method, -mv.amount_cents)
    elif k in (M.CONTRIBUTION, M.COLLECTION, M.OPENING):
        _cash(db, mv, mv.method, mv.amount_cents)
    elif k == M.TRANSFER:
        _cash(db, mv, mv.method, -mv.amount_cents)
        _cash(db, mv, mv.to_method, mv.amount_cents)
    elif k == M.GOAL_SAVING:
        _cash(db, mv, mv.method, -mv.amount_cents)
        _cash(db, mv, "ahorro", mv.amount_cents)
    elif k == M.STOCK_ADJ:
        reason = mv.category or "ajuste"
        delta = mv.quantity if reason == "devolucion" else (-abs(mv.quantity) if reason == "merma" else mv.quantity)
        _stock(db, mv, mv.product_id, delta, reason)
        if mv.amount_cents and reason == "devolucion":
            _cash(db, mv, mv.method, -mv.amount_cents)


def _post_effects(db: Session, business: M.Business, mv: M.Movement) -> None:
    if mv.kind == M.PURCHASE and mv.product_id and mv.unit_cost_cents:
        product = db.get(M.Product, mv.product_id)
        product.cost_cents = mv.unit_cost_cents
    if mv.kind == M.SALE and mv.method == "yape" and mv.paid_cents:
        link_yape(db, business, mv)


def link_yape(db: Session, business: M.Business, mv: M.Movement) -> M.YapePayment | None:
    """Vincula un cobro Yape (notificación) a la venta del mismo monto y día."""
    start = mv.occurred_at - timedelta(hours=12)
    end = mv.occurred_at + timedelta(hours=12)
    pay = db.scalar(select(M.YapePayment).where(
        M.YapePayment.business_id == business.id, M.YapePayment.movement_id.is_(None),
        M.YapePayment.amount_cents == mv.paid_cents,
        M.YapePayment.received_at >= start, M.YapePayment.received_at <= end,
    ).order_by(func.abs(func.julianday(M.YapePayment.received_at) - func.julianday(mv.occurred_at))))
    if pay:
        pay.movement_id = mv.id
        mv.origin = "respaldo_yape"
        if not mv.counterparty:
            mv.counterparty = pay.payer
    return pay


def snapshot(mv: M.Movement) -> dict[str, Any]:
    return {
        "kind": mv.kind, "amount_cents": mv.amount_cents, "paid_cents": mv.paid_cents,
        "method": mv.method, "to_method": mv.to_method, "product_id": mv.product_id,
        "quantity": mv.quantity, "discount_cents": mv.discount_cents,
        "unit_price_ref_cents": mv.unit_price_ref_cents, "category": mv.category,
        "counterparty": mv.counterparty, "description": mv.description,
        "occurred_at": mv.occurred_at.isoformat(), "status": mv.status,
        "expense_type": mv.expense_type, "parent_id": mv.parent_id, "goal_id": mv.goal_id,
        "debt_id": mv.debt_id, "units_pending": mv.units_pending, "origin": mv.origin,
    }


def revise(db: Session, business: M.Business, mv: M.Movement, changes: dict[str, Any], reason: str | None = None,
           commit: bool = True) -> M.Movement:
    """Corrige un movimiento: guarda la versión anterior y recalcula sus efectos."""
    before = snapshot(mv)
    data = {**before, **{k: v for k, v in changes.items() if v is not None or k in ("counterparty",)}}
    if "amount_cents" in changes and mv.kind == M.SALE and before["paid_cents"] == before["amount_cents"] \
            and "paid_cents" not in changes:
        data["paid_cents"] = changes["amount_cents"]
    if mv.kind == M.SALE and "unit_price_ref_cents" not in changes:
        data["unit_price_ref_cents"] = before["unit_price_ref_cents"]
        if changes.get("product_id") and changes["product_id"] != before["product_id"]:
            data["unit_price_ref_cents"] = None
    data["raw_text"] = mv.raw_text
    for e in list(mv.cash_entries):
        db.delete(e)
    for e in list(mv.stock_entries):
        db.delete(e)
    yp = db.scalar(select(M.YapePayment).where(M.YapePayment.movement_id == mv.id))
    if yp:
        yp.movement_id = None
        data["origin"] = "autodeclarado" if not mv.attachments else "con_adjunto"
    db.flush()
    _fill(db, business, mv, data)
    mv.revision += 1
    db.flush()
    _build_effects(db, business, mv)
    _post_effects(db, business, mv)
    db.add(M.MovementRevision(movement_id=mv.id, before=before, after=snapshot(mv), reason=reason))
    if commit:
        db.commit()
    return mv


def void(db: Session, mv: M.Movement, reason: str | None = None, commit: bool = True) -> M.Movement:
    before = snapshot(mv)
    for e in list(mv.cash_entries):
        db.delete(e)
    for e in list(mv.stock_entries):
        db.delete(e)
    yp = db.scalar(select(M.YapePayment).where(M.YapePayment.movement_id == mv.id))
    if yp:
        yp.movement_id = None
    mv.status = "anulado"
    mv.revision += 1
    db.flush()
    db.add(M.MovementRevision(movement_id=mv.id, before=before, after=snapshot(mv), reason=reason or "anulado"))
    if commit:
        db.commit()
    return mv


# ------------------------------------------------------------------ saldos

def pocket_balances(db: Session, business_id: int, until: datetime | None = None) -> dict[str, int]:
    q = select(M.CashEntry.pocket, func.coalesce(func.sum(M.CashEntry.delta_cents), 0)).where(
        M.CashEntry.business_id == business_id)
    if until:
        q = q.where(M.CashEntry.occurred_at < until)
    rows = db.execute(q.group_by(M.CashEntry.pocket)).all()
    out = {"efectivo": 0, "yape": 0, "ahorro": 0}
    out.update({r[0]: int(r[1]) for r in rows})
    return out


def opening_known(db: Session, business_id: int) -> dict[str, bool]:
    rows = db.scalars(select(M.Movement.method).where(
        M.Movement.business_id == business_id, M.Movement.kind == M.OPENING,
        M.Movement.status == "confirmado")).all()
    return {p: p in rows for p in M.POCKETS}


def stock_delta(db: Session, product_id: int, until: datetime | None = None) -> int:
    q = select(func.coalesce(func.sum(M.StockEntry.delta_qty), 0)).where(M.StockEntry.product_id == product_id)
    if until:
        q = q.where(M.StockEntry.occurred_at < until)
    return int(db.scalar(q) or 0)


def expected_stock(db: Session, product: M.Product, until: datetime | None = None) -> int | None:
    if product.initial_stock is None:
        return None
    return product.initial_stock + stock_delta(db, product.id, until)


def sale_pending(db: Session, sale: M.Movement) -> int:
    if sale.kind != M.SALE or sale.status != "confirmado":
        return 0
    collected = db.scalar(select(func.coalesce(func.sum(M.Movement.amount_cents), 0)).where(
        M.Movement.parent_id == sale.id, M.Movement.kind == M.COLLECTION,
        M.Movement.status == "confirmado")) or 0
    return max(0, sale.amount_cents - sale.paid_cents - int(collected))


def receivables(db: Session, business_id: int) -> list[dict[str, Any]]:
    sales = db.scalars(select(M.Movement).where(
        M.Movement.business_id == business_id, M.Movement.kind == M.SALE,
        M.Movement.status == "confirmado", M.Movement.amount_cents > M.Movement.paid_cents,
    ).order_by(M.Movement.occurred_at)).all()
    out = []
    for s in sales:
        pending = sale_pending(db, s)
        if pending > 0:
            out.append({"sale_id": s.id, "counterparty": s.counterparty or "Sin nombre", "pending_cents": pending,
                        "amount_cents": s.amount_cents, "occurred_at": s.occurred_at.isoformat(),
                        "product": s.product.name if s.product else None})
    return out
