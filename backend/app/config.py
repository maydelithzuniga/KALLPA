"""Configuración por variables de entorno (lee también un archivo .env si existe)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()


def _db_url(url: str) -> str:
    """Render/Heroku dan «postgres://…»: SQLAlchemy necesita el driver explícito (psycopg 3)."""
    for pre in ("postgres://", "postgresql://"):
        if url.startswith(pre):
            return "postgresql+psycopg://" + url[len(pre):]
    return url


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "si", "sí"}


@dataclass
class Settings:
    database_url: str = field(default_factory=lambda: _db_url(os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'kallpa.db'}")))
    seed_demo: bool = field(default_factory=lambda: _bool("SEED_DEMO", True))
    notify_auto: bool = field(default_factory=lambda: _bool("NOTIFY_AUTO", True))   # resúmenes y alertas automáticos
    whisper_model: str = field(default_factory=lambda: os.getenv("WHISPER_MODEL", "base"))
    whisper_model_dir: str = field(default_factory=lambda: os.getenv("WHISPER_MODEL_DIR", str(BASE_DIR / "models")))
    whisper_device: str = field(default_factory=lambda: os.getenv("WHISPER_DEVICE", "cpu"))
    whisper_compute_type: str = field(default_factory=lambda: os.getenv("WHISPER_COMPUTE_TYPE", "int8"))
    gemini_enabled: bool = field(default_factory=lambda: _bool("GEMINI_ENABLED", False))
    gemini_api_key: str = field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))
    gemini_model: str = field(default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-3.8-flash"))
    # Agente de IA (Women2) en el chat de la app y en WhatsApp: entiende texto y audio con Gemini
    agent_enabled: bool = field(default_factory=lambda: _bool("AGENT_ENABLED", False))
    agent_model: str = field(default_factory=lambda: os.getenv("AGENT_MODEL", os.getenv("GEMINI_MODEL", "gemini-3.8-flash")))
    agent_voice_reply: bool = field(default_factory=lambda: _bool("AGENT_VOICE_REPLY", True))   # audio Edge-TTS en WhatsApp
    app_base_url: str = field(default_factory=lambda: os.getenv("APP_BASE_URL", "").rstrip("/"))
    whatsapp_enabled: bool = field(default_factory=lambda: _bool("WHATSAPP_ENABLED", False))
    whatsapp_token: str = field(default_factory=lambda: os.getenv("WHATSAPP_TOKEN", ""))
    whatsapp_phone_number_id: str = field(default_factory=lambda: os.getenv("WHATSAPP_PHONE_NUMBER_ID", ""))
    whatsapp_verify_token: str = field(default_factory=lambda: os.getenv("WHATSAPP_VERIFY_TOKEN", ""))
    whatsapp_app_secret: str = field(default_factory=lambda: os.getenv("WHATSAPP_APP_SECRET", ""))
    whatsapp_graph_version: str = field(default_factory=lambda: os.getenv("WHATSAPP_GRAPH_VERSION", "v21.0"))
    # Proveedor de WhatsApp: «meta» (Cloud API oficial) o «twilio» (Sandbox de Twilio: sin verificar negocio)
    whatsapp_provider: str = field(default_factory=lambda: os.getenv("WHATSAPP_PROVIDER", "meta").strip().lower())
    twilio_account_sid: str = field(default_factory=lambda: os.getenv("TWILIO_ACCOUNT_SID", "").strip())
    twilio_auth_token: str = field(default_factory=lambda: os.getenv("TWILIO_AUTH_TOKEN", "").strip())
    twilio_whatsapp_from: str = field(default_factory=lambda: os.getenv("TWILIO_WHATSAPP_FROM", "+14155238886").strip())
    twilio_join_code: str = field(default_factory=lambda: os.getenv("TWILIO_JOIN_CODE", "").strip())
    bridge_secret: str = field(default_factory=lambda: os.getenv("BRIDGE_SECRET", "").strip())   # puente gratis (bridge/)
    twilio_validate: bool = field(default_factory=lambda: _bool("TWILIO_VALIDATE_SIGNATURE", True))
    cors_origins: list[str] = field(
        default_factory=lambda: [o.strip() for o in os.getenv(
            "CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173,capacitor://localhost,http://localhost",
        ).split(",") if o.strip()]
    )

    @property
    def gemini_available(self) -> bool:
        return self.gemini_enabled and bool(self.gemini_api_key)

    @property
    def whatsapp_available(self) -> bool:
        if self.whatsapp_provider == "bridge":
            return self.whatsapp_enabled and bool(self.bridge_secret)
        if self.whatsapp_provider == "twilio":
            return self.whatsapp_enabled and bool(self.twilio_account_sid) and bool(self.twilio_auth_token)
        return (
            self.whatsapp_enabled
            and bool(self.whatsapp_token)
            and bool(self.whatsapp_phone_number_id)
            and bool(self.whatsapp_app_secret)
        )


settings = Settings()
