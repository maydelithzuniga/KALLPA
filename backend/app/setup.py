"""Configuración inicial del negocio: propuesta (Gemini una vez o plantilla local) y guardado."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import gemini
from . import models as M
from .templates import TEMPLATES, local_proposal


def propose(db: Session, business: M.Business, description: str, *, use_ai: bool = True,
            kind: str | None = None) -> dict[str, Any]:
    business.description = description
    proposal: dict[str, Any] | None = None
    note = None
    if use_ai and business.gemini_requests == 0 and kind is None:
        try:
            business.gemini_requests += 1   # límite: una sola solicitud por negocio, aunque falle
            proposal = gemini.propose(description).model_dump()
            proposal["source"] = "gemini"
        except gemini.GeminiUnavailable:
            note = "Usé la plantilla local porque la IA externa no está disponible."
    elif use_ai and business.gemini_requests > 0 and kind is None:
        note = "Ya usé la IA una vez para este negocio; ahora propongo con la plantilla local."
    if proposal is None:
        proposal = local_proposal(description, kind)
    proposal["note"] = note
    business.setup_proposal = proposal
    business.setup_state = "propuesta"
    db.commit()
    return proposal


def proposal_text(p: dict[str, Any]) -> str:
    label = {"reventa": "reventa", "verduras": "verdulería", "comida": "comida preparada", "servicios": "servicios"}[p["kind"]]
    prods = ", ".join(x["name"].lower() for x in p["products"] if not x.get("is_input")) or "aún sin productos"
    pays = " y ".join("Yape" if m == "yape" else "efectivo" for m in p.get("payment_methods", []))
    txt = f"Entendí: negocio de {label}. Vendes {prods}. Cobras en {pays}."
    if p.get("note"):
        txt += " " + p["note"]
    return txt + " ¿Lo guardo así? Los precios y el stock me los dices cuando quieras."


def apply(db: Session, business: M.Business, proposal: dict[str, Any] | None = None, *, source: str | None = None) -> M.Business:
    p = proposal or business.setup_proposal
    if not p:
        raise ValueError("No hay propuesta")
    business.kind = p["kind"]
    if p.get("business_name") and (not business.name or business.name == "Mi negocio"):
        business.name = p["business_name"]
    business.payment_methods = p.get("payment_methods") or ["efectivo", "yape"]
    for c in db.scalars(select(M.Category).where(M.Category.business_id == business.id)).all():
        db.delete(c)
    for c in p["categories"]:
        db.add(M.Category(business_id=business.id, name=c["name"], kind=c["kind"]))
    existing = {x.name.lower() for x in business.products}
    for pr in p["products"]:
        if pr["name"].lower() in existing:
            continue
        db.add(M.Product(business_id=business.id, name=pr["name"], aliases=pr.get("aliases", []),
                         is_service=pr.get("is_service", False), is_input=pr.get("is_input", False),
                         track_stock=pr.get("track_stock", p["kind"] == "reventa"), unit=pr.get("unit", "unidad"),
                         price_cents=None, cost_cents=None, initial_stock=None))
    business.setup_state = "listo"
    business.setup_source = source or p.get("source", "plantilla")
    db.commit()
    return business


def from_template(db: Session, business: M.Business, kind: str) -> M.Business:
    if kind not in TEMPLATES:
        raise ValueError("Plantilla desconocida")
    p = local_proposal(business.description or "", kind)
    p["products"] = [dict(x) for x in TEMPLATES[kind]["products"]]
    return apply(db, business, p, source="plantilla")
