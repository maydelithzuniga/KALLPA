"""Una sola puerta de entrada para todo lo que manda la emprendedora: texto o audio, por la app o por WhatsApp.

1. Idempotencia: el mismo message_id (o el id de WhatsApp) nunca se procesa dos veces.
2. Audio: si el agente de IA está activo, Gemini lo escucha y entiende (multimodal, como Women2);
   si no, se transcribe en el servidor con faster-whisper y se interpreta con las reglas locales.
3. Texto: si el agente está activo y no hay una pregunta pendiente, Gemini lo interpreta; si no, reglas locales.
4. Todo pasa por conversation.process_message → mismos registros, misma caja, mismas respuestas en ambos canales.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import agent, transcribe
from . import models as M
from .conversation import process_message

log = logging.getLogger(__name__)


class NotUnderstood(RuntimeError):
    pass


def _pending(db: Session, b: M.Business, conversation: str) -> bool:
    """¿Hay una pregunta abierta (o la primera conversación)? Entonces respondemos con reglas, sin gastar IA."""
    if b.setup_state != "listo":
        return True
    return db.scalar(select(M.Draft.id).where(M.Draft.business_id == b.id, M.Draft.conversation == conversation,
                                              M.Draft.status == "abierto")) is not None


def receive(db: Session, b: M.Business, *, message_id: str, channel: str, conversation: str | None = None,
            text: str | None = None, audio: bytes | None = None, mime_type: str = "audio/ogg", suffix: str = ".ogg",
            op_id: str | None = None, occurred_at: datetime | None = None) -> dict[str, Any]:
    conv = conversation or f"{channel}:{b.id}"
    prev = db.scalar(select(M.ProcessedMessage).where(M.ProcessedMessage.message_id == message_id))
    if prev:
        r = dict(prev.response)
        r["duplicate"] = True
        return r
    agent_data = None
    via_voice = audio is not None
    if audio is not None:
        if agent.enabled():
            try:
                agent_data = agent.analyze(db, b, audio=audio, mime_type=mime_type)
                text = agent_data.get("transcripcion") or ""
            except agent.AgentUnavailable as e:
                log.info("Agente no disponible para audio, uso Whisper: %s", e)
        if agent_data is None:
            text = transcribe.transcribe_bytes(audio, suffix)   # puede lanzar TranscriptionUnavailable
        if not (text or "").strip():
            raise NotUnderstood("No escuché bien el audio")
    elif agent.enabled() and text and not _pending(db, b, conv):
        try:
            agent_data = agent.analyze(db, b, text=text)
        except agent.AgentUnavailable as e:
            log.info("Agente no disponible para texto, uso reglas: %s", e)
    if agent_data is not None and _pending(db, b, conv):
        agent_data = None   # responde a la pregunta abierta con el texto/transcripción
    return process_message(db, b, text or "", message_id=message_id, channel=channel, conversation=conv, op_id=op_id,
                           occurred_at=occurred_at, via_voice=via_voice, transcript=text if via_voice else None,
                           agent_data=agent_data)
