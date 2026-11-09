"""Verificación de movimientos por Yape (en el MVP, con registros de Yape de demostración)."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from . import ledger
from . import models as M
from .timeutil import LIMA, now_lima


def yape_verify(db: Session, b: M.Business, body: dict[str, Any]) -> dict[str, Any]:
    """Crea un registro de Yape (simulado) y lo vincula al movimiento indicado o al que coincida en monto y día."""
    mv = db.get(M.Movement, int(body["movement_id"])) if body.get("movement_id") else None
    if mv is not None and (mv.business_id != b.id or ledger.yape_direction(mv) is None):
        return {"linked_movement_id": None, "error": "Ese movimiento no es por Yape"}
    direction = ledger.yape_direction(mv) if mv else body.get("direction", "entrada")
    amount = mv.paid_cents if mv else int(body["amount_cents"])
    when = body.get("received_at")
    if isinstance(when, str):
        when = datetime.fromisoformat(when.replace("Z", "+00:00"))
    if when is not None and getattr(when, "tzinfo", None) is not None:
        when = when.astimezone(LIMA).replace(tzinfo=None)
    when = when or (mv.occurred_at if mv else now_lima())
    y = M.YapePayment(business_id=b.id, direction=direction, payer=body.get("payer") or (mv.counterparty if mv and mv.counterparty else "Cliente Yape"),
                      amount_cents=amount, operation_code=body.get("operation_code") or f"DEMO-{uuid.uuid4().hex[:8].upper()}",
                      received_at=when, demo=True)
    db.add(y)
    db.flush()
    target = mv or None
    if target is None:
        from sqlalchemy import select
        kinds = M.YAPE_IN_KINDS if direction == "entrada" else M.YAPE_OUT_KINDS
        cands = db.scalars(select(M.Movement).where(M.Movement.business_id == b.id, M.Movement.method == "yape",
                                                    M.Movement.kind.in_(kinds), M.Movement.paid_cents == amount,
                                                    M.Movement.status == "confirmado").order_by(M.Movement.occurred_at.desc())).all()
        for c in cands:
            if ledger.yape_verified(db, c) is None and abs((c.occurred_at - when).total_seconds()) < 12 * 3600:
                target = c
                break
    if target is not None and ledger.yape_verified(db, target) is None:
        y.movement_id = target.id
        target.origin = "respaldo_yape"
        if not target.counterparty and direction == "entrada":
            target.counterparty = y.payer
    db.commit()
    return {"id": y.id, "linked_movement_id": y.movement_id, "direction": direction}
