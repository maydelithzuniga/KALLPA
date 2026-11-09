"""Agente de IA (integración del agente de Women2: github.com/maydelithzuniga/Women2).

Es el mismo cerebro para el chat de la app y para WhatsApp. Acepta texto o audio:
- Gemini (multimodal) escucha/lee el mensaje con el contexto del negocio y devuelve un JSON con la intención
  (mismo formato que `ai_advisor.py` de Women2, ampliado con gasto, pérdida, cobro de fiado, retiro y cierre).
- La intención NO se guarda directo: pasa por el motor de Kallpa (conversation.Engine), que valida, pregunta lo
  que falta, evita duplicados y actualiza caja e inventario. Así app y WhatsApp usan una sola fuente de datos.
- Si no hay clave de Gemini o falla, Kallpa sigue funcionando con sus reglas locales (y Whisper para audio).
- Respuesta por voz con Edge-TTS (voz es-PE-CamilaNeural), como en Women2, para enviarla por WhatsApp.
"""
from __future__ import annotations

import base64
import json
import logging
import os
from datetime import timedelta
from typing import Any

import httpx

from .config import settings

log = logging.getLogger(__name__)

SYSTEM_PROMPT_TEMPLATE = """Eres el Asesor Financiero e Inteligencia de Negocio para una MYPE peruana. Hablas como una amiga que sabe de números.

CONTEXTO ACTUAL DEL NEGOCIO:
{negocio_metrics_json}

INSTRUCCIONES DE CLASIFICACIÓN (audio o texto):
Analiza el mensaje de la emprendedora y determina si se trata de:
1. VENTA: "Vendí [cantidad] [producto] a [monto] soles en [yape/efectivo]". Puede nombrar varios productos.
   Las cantidades pueden ser kilos, medio kilo, un cuarto, jabas, sacos, atados o "3 soles de tomate".
   Si dice que le quedaron debiendo o "fiado", marca fiado=true y la persona.
2. COMPRA: "Compré [cantidad] [producto] a [monto] soles en [yape/efectivo] para inventario".
3. GASTO: pagos del negocio (luz, alquiler, pasajes, bolsas, gas, sueldos).
4. RETIRO: plata que sacó del negocio para la casa.
5. PERDIDA: algo que se malogró, venció, rompió, se perdió, o plata robada/billete falso.
6. COBRO_FIADO: un cliente le pagó lo que debía.
7. META: "He separado/depositado [monto] soles para la meta [nombre]".
8. CIERRE: quiere cerrar su día o contar su plata.
9. CONSULTA: preguntas sobre su negocio, finanzas o recomendaciones (usa el contexto y sus números).

Usa los nombres de productos del contexto cuando coincidan. No inventes montos: si no los dijo, usa null.

FORMATO DE RESPUESTA OBLIGATORIO (JSON ESTRICTO):
{{
  "transcripcion": "lo que dijo la emprendedora, palabra por palabra",
  "intent": {{
    "tipo": "venta | compra | gasto | retiro | perdida | cobro_fiado | meta | cierre | consulta",
    "items": [{{"producto": "nombre o null", "cantidad": 1, "unidad": "kg | unidad | jaba | saco | atado | soles | null", "monto": 0.0}}],
    "monto": 0.0,
    "metodo_pago": "yape | efectivo | null",
    "persona": "nombre o null",
    "fiado": false,
    "nombre_meta": "nombre de la meta o null",
    "descripcion": "detalle corto o null"
  }},
  "respuesta_voz": "Texto empático y directo (máximo 2 párrafos) para responder en voz alta. Si es consulta, responde con sus números."
}}
"""

RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "transcripcion": {"type": "STRING"},
        "intent": {"type": "OBJECT", "properties": {
            "tipo": {"type": "STRING", "enum": ["venta", "compra", "gasto", "retiro", "perdida", "cobro_fiado", "meta", "cierre", "consulta"]},
            "items": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
                "producto": {"type": "STRING", "nullable": True}, "cantidad": {"type": "NUMBER", "nullable": True},
                "unidad": {"type": "STRING", "nullable": True}, "monto": {"type": "NUMBER", "nullable": True}}}},
            "monto": {"type": "NUMBER", "nullable": True},
            "metodo_pago": {"type": "STRING", "nullable": True},
            "persona": {"type": "STRING", "nullable": True},
            "fiado": {"type": "BOOLEAN", "nullable": True},
            "nombre_meta": {"type": "STRING", "nullable": True},
            "descripcion": {"type": "STRING", "nullable": True}},
            "required": ["tipo"]},
        "respuesta_voz": {"type": "STRING"},
    },
    "required": ["intent", "respuesta_voz"],
}


class AgentUnavailable(RuntimeError):
    pass


def enabled() -> bool:
    return settings.agent_enabled and bool(settings.gemini_api_key)


def business_context(db, b) -> dict[str, Any]:
    """Equivalente a get_business_metrics() de Women2, con los datos de Kallpa."""
    from . import ledger, metrics, units
    from .timeutil import today_lima
    today = today_lima()
    day = metrics.day_stats(db, b, today)
    month = metrics.period_stats(db, b, today.replace(day=1), today + timedelta(days=1))
    cash = metrics.cash_position(db, b)
    goals = [g for g in metrics.goals(db, b) if g["status"] == "activa"]
    prods = []
    for i in metrics.inventory(db, b)[:40]:
        prods.append({"nombre": i["name"], "unidad": i["unit"], "precio_venta": (i["price_cents"] or 0) / 100 or None,
                      "precio_compra": (i["cost_cents"] or 0) / 100 or None, "stock_actual": i["expected_stock"],
                      "se_vende": i.get("spec_text", {}).get("vende"), "se_compra": i.get("spec_text", {}).get("compra")})
    return {
        "negocio": {"id": b.id, "nombre": b.name, "tipo": b.kind, "duena": b.owner_name},
        "productos": prods,
        "ventas": {"hoy": day["sales_cents"] / 100, "mes_actual": month["sales_cents"] / 100},
        "ganancia": {"hoy": day["profit_cents"] / 100, "mes_actual": month["profit_cents"] / 100},
        "caja": {"efectivo": cash["efectivo_cents"] / 100, "yape": cash["yape_cents"] / 100, "completa": cash["complete"]},
        "fiados_por_cobrar": [{"persona": r["counterparty"], "monto": r["pending_cents"] / 100} for r in ledger.receivables(db, b.id)][:10],
        "metas": [{"nombre": g["name"], "avance_pct": g.get("progress_pct"), "meta": g["target_cents"] / 100} for g in goals],
        "unidades_validas": sorted(units.UNIT_NAMES),
    }


def analyze(db, b, *, text: str | None = None, audio: bytes | None = None, mime_type: str = "audio/ogg",
            timeout: float = 9.0) -> dict[str, Any]:
    """process_user_audio() de Women2, ahora para audio o texto. Devuelve {transcripcion, intent, respuesta_voz}."""
    if not enabled():
        raise AgentUnavailable("Agente de IA desactivado o sin GEMINI_API_KEY")
    ctx = json.dumps(business_context(db, b), ensure_ascii=False)
    system = SYSTEM_PROMPT_TEMPLATE.format(negocio_metrics_json=ctx)
    parts: list[dict[str, Any]] = []
    if audio is not None:
        parts.append({"inline_data": {"mime_type": mime_type, "data": base64.b64encode(audio).decode()}})
        parts.append({"text": "Escucha el audio, transcríbelo, clasifica la transacción en JSON y genera el texto de respuesta."})
    else:
        parts.append({"text": f"Mensaje de la emprendedora: «{text}». Clasifícalo en JSON y genera el texto de respuesta."})
    body = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {"responseMimeType": "application/json", "responseSchema": RESPONSE_SCHEMA, "temperature": 0.1},
    }
    if _thinking_ok and _thinking_ok[0]:   # misma forma de «pensar poco» que ya funcionó al transcribir
        body["generationConfig"]["thinkingConfig"] = _thinking_ok[0]
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.agent_model}:generateContent"
    try:
        r = httpx.post(url, json=body, headers={"x-goog-api-key": settings.gemini_api_key}, timeout=timeout)
        r.raise_for_status()
        raw = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        data = json.loads(raw)
    except (httpx.HTTPError, KeyError, IndexError, json.JSONDecodeError) as e:
        log.warning("Agente IA falló: %s", e)
        raise AgentUnavailable(str(e)) from e
    data.setdefault("intent", {"tipo": "consulta"})
    data.setdefault("respuesta_voz", "")
    data["transcripcion"] = (data.get("transcripcion") or text or "").strip()
    return data


# Qué forma de «pensar poco» acepta el modelo (se descubre en la primera llamada y se recuerda).
_THINKING_OPTIONS = [{"thinkingLevel": "low"}, {"thinkingBudget": 0}, None]
_thinking_ok: list[Any] = []

TRANSCRIBE_PROMPT = ("Transcribe exactamente lo que dice este audio en español de Perú. Es una emprendedora contando "
                     "ventas, gastos o preguntas de su negocio. Escribe los montos y cantidades con números "
                     "(«dos kilos» → «2 kilos», «tres soles cincuenta» → «3.50 soles»). Devuelve SOLO el texto, sin comillas.")


def transcribe_audio(audio: bytes, mime_type: str = "audio/ogg", timeout: float = 9.0) -> str:
    """Solo transcribe (rápido): luego las reglas de Kallpa entienden el texto igual que si lo hubiera escrito.
    WhatsApp por Twilio espera máximo 15 s la respuesta, así que esto tiene que ser corto."""
    if not enabled():
        raise AgentUnavailable("Agente de IA desactivado o sin GEMINI_API_KEY")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.agent_model}:generateContent"
    parts = [{"inline_data": {"mime_type": mime_type, "data": base64.b64encode(audio).decode()}}, {"text": TRANSCRIBE_PROMPT}]
    options = _thinking_ok[:1] or _THINKING_OPTIONS
    last: Exception | None = None
    for th in options:
        gen: dict[str, Any] = {"temperature": 0, "maxOutputTokens": 400}
        if th:
            gen["thinkingConfig"] = th
        body = {"contents": [{"role": "user", "parts": parts}], "generationConfig": gen}
        try:
            r = httpx.post(url, json=body, headers={"x-goog-api-key": settings.gemini_api_key}, timeout=timeout)
            if r.status_code == 400 and th is not None and not _thinking_ok:
                last = RuntimeError(r.text[:200])
                continue   # este modelo no acepta esa opción: pruebo la siguiente
            r.raise_for_status()
            cand = r.json()["candidates"][0]
            text = "".join(p.get("text", "") for p in cand.get("content", {}).get("parts", []) if not p.get("thought"))
            if not _thinking_ok:
                _thinking_ok.append(th)
            return text.strip().strip("«»\"")
        except (httpx.HTTPError, KeyError, IndexError) as e:
            log.warning("Gemini no pudo transcribir: %s", e)
            raise AgentUnavailable(str(e)) from e
    raise AgentUnavailable(f"Gemini rechazó la configuración: {last}")


async def text_to_speech_edge(text: str, output_path: str) -> str:
    """text_to_speech_edge() de Women2: voz peruana con Edge-TTS (gratis)."""
    import edge_tts
    communicate = edge_tts.Communicate(text, voice=os.getenv("EDGE_TTS_VOICE", "es-PE-CamilaNeural"))
    await communicate.save(output_path)
    return output_path
