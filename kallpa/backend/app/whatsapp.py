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


def send_text(to: str, body: str, quick_replies: list[str] | None = None) -> None:
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
