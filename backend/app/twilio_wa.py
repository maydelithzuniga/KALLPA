"""WhatsApp por Twilio (Sandbox o número aprobado en Twilio). No requiere verificar el negocio en Meta.

- POST /webhook/twilio   Twilio envía cada mensaje (form-urlencoded). Se valida X-Twilio-Signature con TWILIO_AUTH_TOKEN.
- Respuestas: API REST de Twilio (Messages.json), así el audio largo no hace esperar al webhook.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
from typing import Any, Mapping

import httpx

from .config import settings

log = logging.getLogger(__name__)
API = "https://api.twilio.com/2010-04-01"


def _auth() -> tuple[str, str]:
    return (settings.twilio_account_sid, settings.twilio_auth_token)


def signature_for(url: str, params: Mapping[str, str]) -> str:
    data = url + "".join(k + params[k] for k in sorted(params))
    mac = hmac.new(settings.twilio_auth_token.encode(), data.encode(), hashlib.sha1).digest()
    return base64.b64encode(mac).decode()


def verify_signature(candidate_urls: list[str], params: Mapping[str, str], header: str | None) -> bool:
    if not settings.twilio_validate:
        return True
    if not settings.twilio_auth_token or not header:
        return False
    return any(hmac.compare_digest(signature_for(u, params), header) for u in candidate_urls if u)


def phone_of(addr: str) -> str:
    """'whatsapp:+51919142871' -> '51919142871' (mismo formato que Business.phone)."""
    return "".join(ch for ch in (addr or "") if ch.isdigit())


def extract_message(form: Mapping[str, str]) -> dict[str, Any] | None:
    sid = form.get("MessageSid") or form.get("SmsMessageSid")
    frm = phone_of(form.get("From", ""))
    if not sid or not frm:
        return None
    item: dict[str, Any] = {"id": sid, "from": frm, "type": "text", "text": (form.get("Body") or "").strip() or None}
    try:
        n = int(form.get("NumMedia") or 0)
    except ValueError:
        n = 0
    for i in range(n):
        ctype = form.get(f"MediaContentType{i}", "")
        if ctype.startswith("audio/"):
            item.update(type="audio", media_url=form.get(f"MediaUrl{i}"), mime=ctype)
            break
    return item


def download_media(url: str) -> bytes:
    with httpx.Client(timeout=30, follow_redirects=True) as c:
        r = c.get(url, auth=_auth())
        r.raise_for_status()
        return r.content


def _from() -> str:
    f = settings.twilio_whatsapp_from
    return f if f.startswith("whatsapp:") else f"whatsapp:{'+' + f.lstrip('+')}"


# Respuesta «en línea» (TwiML): mientras se atiende un mensaje entrante, las respuestas se juntan aquí y
# salen en la misma respuesta HTTP del webhook. No usa la API REST (que exige perfil KYC aprobado en Twilio).
import threading  # noqa: E402
from xml.sax.saxutils import escape  # noqa: E402

_local = threading.local()


def collect_start() -> None:
    _local.items = []


def collect_end() -> list[dict[str, str | None]]:
    items = getattr(_local, "items", None) or []
    _local.items = None
    return items


def twiml(items: list[dict[str, str | None]]) -> str:
    parts = []
    for it in items:
        inner = (f"<Body>{escape(it['body'] or '')}</Body>" if it.get("body") else "") + \
                (f"<Media>{escape(it['media_url'])}</Media>" if it.get("media_url") else "")
        if inner:
            parts.append(f"<Message>{inner}</Message>")
    return '<?xml version="1.0" encoding="UTF-8"?><Response>' + "".join(parts) + "</Response>"


def send(to: str, body: str | None = None, media_url: str | None = None) -> bool:
    items = getattr(_local, "items", None)
    if items is not None:   # respondiendo a un mensaje entrante: va en el TwiML
        items.append({"body": body[:1600] if body else None, "media_url": media_url})
        return True
    data = {"From": _from(), "To": f"whatsapp:+{phone_of(to)}"}
    if body:
        data["Body"] = body[:1600]
    if media_url:
        data["MediaUrl"] = media_url
    try:
        r = httpx.post(f"{API}/Accounts/{settings.twilio_account_sid}/Messages.json", data=data, auth=_auth(), timeout=20)
        r.raise_for_status()
        return True
    except httpx.HTTPError as e:
        detail = getattr(getattr(e, "response", None), "text", "")
        log.error("No se pudo enviar por Twilio: %s %s", e, detail[:300])
        return False


def send_text(to: str, body: str, quick_replies: list[str] | None = None) -> bool:
    if quick_replies:   # Twilio Sandbox no tiene botones: se sugieren como texto
        body = body + "\n\nResponde: " + " · ".join(quick_replies[:4])
    return send(to, body=body)
