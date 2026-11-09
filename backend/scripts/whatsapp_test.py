"""Prueba directa de WhatsApp Cloud API (basado en test_whatsapp.py de Women2).

Uso:  python scripts/whatsapp_test.py --to 51987654321
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

from app.config import settings  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description="Enviar un mensaje de prueba por WhatsApp")
    ap.add_argument("--to", required=True, help="Celular con código de país, ej. 51987654321")
    ap.add_argument("--text", default="👋 Hola, soy Kallpa. ¡La conexión con WhatsApp funciona! Mándame tus ventas por audio o texto.")
    a = ap.parse_args()
    if not settings.whatsapp_token or not settings.whatsapp_phone_number_id:
        sys.exit("Falta WHATSAPP_TOKEN o WHATSAPP_PHONE_NUMBER_ID en backend/.env")
    url = f"https://graph.facebook.com/{settings.whatsapp_graph_version}/{settings.whatsapp_phone_number_id}/messages"
    r = httpx.post(url, headers={"Authorization": f"Bearer {settings.whatsapp_token}"}, timeout=15,
                   json={"messaging_product": "whatsapp", "recipient_type": "individual",
                         "to": "".join(ch for ch in a.to if ch.isdigit()), "type": "text", "text": {"body": a.text}})
    print("✅ Enviado" if r.status_code in (200, 201) else f"❌ Error {r.status_code}: {r.text}")


if __name__ == "__main__":
    main()
