"""WhatsApp Cloud API oficial de Meta: solo transporta mensajes y audios.

- GET  /webhook/whatsapp  verificación (hub.challenge) con WHATSAPP_VERIFY_TOKEN
- POST /webhook/whatsapp  valida X-Hub-Signature-256 con WHATSAPP_APP_SECRET
Las credenciales viven solo en el servidor (variables de entorno).
"""
from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Any

import httpx

from .config import settings

log = logging.getLogger(__name__)
GRAPH = "https://graph.facebook.com"


def verify_signature(raw_body: bytes, header: str | None) -> bool:
    if not settings.whatsapp_app_secret or not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(settings.whatsapp_app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.split("=", 1)[1])


def extract_messages(payload: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for msg in value.get("messages", []) or []:
                item = {"id": msg.get("id"), "from": msg.get("from"), "type": msg.get("type"),
                        "timestamp": msg.get("timestamp")}
                if msg.get("type") == "text":
                    item["text"] = msg.get("text", {}).get("body", "")
                elif msg.get("type") == "audio":
                    item["media_id"] = msg.get("audio", {}).get("id")
                elif msg.get("type") == "interactive":
                    inter = msg.get("interactive", {})
                    item["text"] = (inter.get("button_reply") or inter.get("list_reply") or {}).get("title", "")
                elif msg.get("type") == "button":
                    item["text"] = msg.get("button", {}).get("text", "")
                out.append(item)
    return out


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {settings.whatsapp_token}"}


def download_media(media_id: str) -> bytes:
    base = f"{GRAPH}/{settings.whatsapp_graph_version}"
    with httpx.Client(timeout=30) as c:
        meta = c.get(f"{base}/{media_id}", headers=_headers())
        meta.raise_for_status()
        url = meta.json()["url"]
        data = c.get(url, headers=_headers())
        data.raise_for_status()
        return data.content


def _twilio() -> bool:
    return settings.whatsapp_provider == "twilio"


# ---- Puente gratis (carpeta bridge/): los mensajes salientes esperan aquí y el puente los recoge.
import threading  # noqa: E402
from collections import deque  # noqa: E402

_outbox: deque = deque(maxlen=500)
_outbox_lock = threading.Lock()


def _bridge() -> bool:
    return settings.whatsapp_provider == "bridge"


def bridge_queue(to: str, text: str | None = None, audio_url: str | None = None) -> None:
    with _outbox_lock:
        _outbox.append({"to": "".join(ch for ch in to if ch.isdigit()), "text": text, "audio_url": audio_url})


def bridge_drain() -> list[dict[str, Any]]:
    with _outbox_lock:
        items = list(_outbox)
        _outbox.clear()
    return items


def send_text(to: str, body: str, quick_replies: list[str] | None = None) -> None:
    if _bridge():
        bridge_queue(to, body + ("\n\nResponde: " + " · ".join(quick_replies[:4]) if quick_replies else ""))
        return
    if _twilio():
        from . import twilio_wa
        twilio_wa.send_text(to, body, quick_replies)
        return
    base = f"{GRAPH}/{settings.whatsapp_graph_version}/{settings.whatsapp_phone_number_id}/messages"
    if quick_replies:
        buttons = [{"type": "reply", "reply": {"id": f"q{i}", "title": q[:20]}} for i, q in enumerate(quick_replies[:3])]
        payload = {"messaging_product": "whatsapp", "to": to, "type": "interactive",
                   "interactive": {"type": "button", "body": {"text": body[:1024]}, "action": {"buttons": buttons}}}
    else:
        payload = {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": body[:4096]}}
    try:
        r = httpx.post(base, json=payload, headers=_headers(), timeout=20)
        r.raise_for_status()
    except httpx.HTTPError as e:
        log.error("No se pudo enviar a WhatsApp: %s", e)


# ------------------------------------------------------------------ voz y plantillas (del agente Women2)
import asyncio  # noqa: E402
from pathlib import Path  # noqa: E402

VOICE_DIR = Path(__file__).resolve().parent.parent / "voice"
VOICE_DIR.mkdir(exist_ok=True)


def send_voice_reply(to: str, text: str, message_id: str) -> None:
    """Responde también con un audio (Edge-TTS, voz es-PE-CamilaNeural). Necesita APP_BASE_URL público."""
    if not settings.agent_voice_reply or not settings.app_base_url:
        return
    try:
        from .agent import text_to_speech_edge
        name = "r_" + "".join(ch for ch in message_id if ch.isalnum())[-40:] + ".mp3"
        # máximo 3 s: la respuesta escrita no puede esperar a la voz (WhatsApp por Twilio espera 15 s en total)
        asyncio.run(asyncio.wait_for(text_to_speech_edge(text.replace("✓", "").replace("·", ","), str(VOICE_DIR / name)), 3))
    except Exception as e:  # noqa: BLE001 (edge-tts no instalado o sin red)
        log.info("Sin respuesta de voz: %s", e)
        return
    if _bridge():
        bridge_queue(to, audio_url=f"{settings.app_base_url}/audio/{name}")
        return
    if _twilio():
        from . import twilio_wa
        twilio_wa.send(to, media_url=f"{settings.app_base_url}/audio/{name}")
        return
    base = f"{GRAPH}/{settings.whatsapp_graph_version}/{settings.whatsapp_phone_number_id}/messages"
    payload = {"messaging_product": "whatsapp", "recipient_type": "individual", "to": to, "type": "audio",
               "audio": {"link": f"{settings.app_base_url}/audio/{name}"}}
    try:
        httpx.post(base, json=payload, headers=_headers(), timeout=20).raise_for_status()
    except httpx.HTTPError as e:
        log.error("No se pudo enviar el audio: %s", e)


def send_document(to: str, url: str, filename: str = "Informe_financiero.pdf") -> None:
    """Manda un PDF (el informe) como archivo adjunto en el chat."""
    if _bridge():
        bridge_queue(to, f"📄 Descarga tu informe: {url}")
        return
    if _twilio():
        from . import twilio_wa
        twilio_wa.send(to, media_url=url)
        return
    base = f"{GRAPH}/{settings.whatsapp_graph_version}/{settings.whatsapp_phone_number_id}/messages"
    payload = {"messaging_product": "whatsapp", "to": to, "type": "document", "document": {"link": url, "filename": filename}}
    try:
        httpx.post(base, json=payload, headers=_headers(), timeout=20).raise_for_status()
    except httpx.HTTPError as e:
        log.error("No se pudo enviar el documento: %s", e)


def send_template(to: str, template_name: str, parameters: list[str], language_code: str = "es") -> bool:
    """Plantillas de utilidad (send_whatsapp_utility_template de Women2): para escribirle primero, fuera de las 24 h."""
    if _bridge():
        bridge_queue(to, " · ".join(str(p) for p in parameters))
        return True
    if _twilio():   # en el Sandbox de Twilio se envía como texto (funciona dentro de las 24 h)
        from . import twilio_wa
        return twilio_wa.send_text(to, " · ".join(str(p) for p in parameters))
    base = f"{GRAPH}/{settings.whatsapp_graph_version}/{settings.whatsapp_phone_number_id}/messages"
    payload = {"messaging_product": "whatsapp", "recipient_type": "individual", "to": to, "type": "template",
               "template": {"name": template_name, "language": {"code": language_code},
                            "components": [{"type": "body", "parameters": [{"type": "text", "text": str(p)[:1000]} for p in parameters]}]}}
    try:
        httpx.post(base, json=payload, headers=_headers(), timeout=20).raise_for_status()
        return True
    except httpx.HTTPError as e:
        log.error("No se pudo enviar la plantilla: %s", e)
        return False
