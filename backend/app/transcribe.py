"""Transcripción local con faster-whisper (modelo multilingüe «base», CPU, int8).

El modelo se descarga antes de la demo con scripts/download_model.py y se carga desde disco.
"""
from __future__ import annotations

import logging
import os
import tempfile
import threading
from pathlib import Path

from .config import settings

log = logging.getLogger(__name__)
_model = None
_lock = threading.Lock()
_error: str | None = None


class TranscriptionUnavailable(RuntimeError):
    pass


def model_path() -> Path:
    return Path(settings.whisper_model_dir) / f"faster-whisper-{settings.whisper_model}"


def status() -> dict:
    try:
        import faster_whisper  # noqa: F401
        installed = True
    except Exception:  # pragma: no cover
        installed = False
    return {"installed": installed, "model_on_disk": model_path().exists(), "loaded": _model is not None,
            "model": settings.whisper_model, "error": _error}


def _load():
    global _model, _error
    if _model is not None:
        return _model
    with _lock:
        if _model is not None:
            return _model
        try:
            from faster_whisper import WhisperModel
        except Exception as e:  # pragma: no cover
            _error = "faster-whisper no está instalado"
            raise TranscriptionUnavailable(_error) from e
        path = model_path()
        if not path.exists():
            _error = f"Modelo no encontrado en {path}. Ejecuta: python scripts/download_model.py"
            raise TranscriptionUnavailable(_error)
        _model = WhisperModel(str(path), device=settings.whisper_device, compute_type=settings.whisper_compute_type)
        _error = None
        return _model


PROMPT = ("Vendí tres polos a veinte soles por Yape. Compré una docena por ciento cuarenta y cuatro en efectivo. "
          "Gasté cuarenta en mercadería. Sí, guárdalo. Me debe. Fiado.")


def transcribe_bytes(data: bytes, suffix: str = ".webm") -> str:
    model = _load()
    fd, tmp = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        segments, _info = model.transcribe(tmp, language="es", beam_size=1, vad_filter=True,
                                           initial_prompt=PROMPT, condition_on_previous_text=False)
        return " ".join(s.text.strip() for s in segments).strip()
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
