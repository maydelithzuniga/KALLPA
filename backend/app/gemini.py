"""Única llamada a Gemini por negocio: proponer la estructura inicial.

Solo se envía la descripción del rubro y los productos o servicios habituales.
Nunca se envían ventas, compras, transcripciones diarias ni reportes.
"""
from __future__ import annotations

import json
import logging
from typing import Literal

import httpx
from pydantic import BaseModel, Field, ValidationError

from .config import settings

log = logging.getLogger(__name__)


class ProposedCategory(BaseModel):
    name: str = Field(max_length=60)
    kind: Literal["venta", "compra", "gasto_fijo", "gasto_variable", "personal"]


class ProposedProduct(BaseModel):
    name: str = Field(max_length=80)
    aliases: list[str] = Field(default_factory=list, max_length=8)
    is_service: bool = False
    is_input: bool = False
    track_stock: bool = True
    unit: str = "unidad"


class BusinessProposal(BaseModel):
    kind: Literal["reventa", "verduras", "comida", "servicios"]
    business_name: str | None = None
    categories: list[ProposedCategory] = Field(max_length=15)
    products: list[ProposedProduct] = Field(max_length=15)
    payment_methods: list[Literal["efectivo", "yape"]] = Field(default_factory=lambda: ["efectivo", "yape"])


SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "kind": {"type": "STRING", "enum": ["reventa", "verduras", "comida", "servicios"]},
        "business_name": {"type": "STRING", "nullable": True},
        "categories": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
            "name": {"type": "STRING"},
            "kind": {"type": "STRING", "enum": ["venta", "compra", "gasto_fijo", "gasto_variable", "personal"]}},
            "required": ["name", "kind"]}},
        "products": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
            "name": {"type": "STRING"}, "aliases": {"type": "ARRAY", "items": {"type": "STRING"}},
            "is_service": {"type": "BOOLEAN"}, "is_input": {"type": "BOOLEAN"},
            "track_stock": {"type": "BOOLEAN"}, "unit": {"type": "STRING"}},
            "required": ["name", "aliases"]}},
        "payment_methods": {"type": "ARRAY", "items": {"type": "STRING", "enum": ["efectivo", "yape"]}},
    },
    "required": ["kind", "categories", "products", "payment_methods"],
}

PROMPT = """Eres asistente para microemprendedoras del Perú. A partir de la descripción del negocio,
propone su estructura inicial: tipo (reventa, comida o servicios), categorías de ingresos y gastos,
productos o servicios habituales con nombres alternativos como los diría una persona en Lima
(plural, diminutivos, nombres cortos) y medios de pago. NO inventes precios, costos ni stock.
Descripción: «{description}»"""


class GeminiUnavailable(RuntimeError):
    pass


def propose(description: str, timeout: float = 20.0) -> BusinessProposal:
    if not settings.gemini_available:
        raise GeminiUnavailable("Gemini desactivado o sin clave")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.gemini_model}:generateContent"
    body = {
        "contents": [{"role": "user", "parts": [{"text": PROMPT.format(description=description[:600])}]}],
        "generationConfig": {"responseMimeType": "application/json", "responseSchema": SCHEMA, "temperature": 0.2},
    }
    try:
        r = httpx.post(url, json=body, headers={"x-goog-api-key": settings.gemini_api_key}, timeout=timeout)
        r.raise_for_status()
        text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        return BusinessProposal.model_validate(json.loads(text))
    except (httpx.HTTPError, KeyError, IndexError, json.JSONDecodeError, ValidationError) as exc:
        log.warning("Gemini falló: %s", exc)
        raise GeminiUnavailable(str(exc)) from exc
