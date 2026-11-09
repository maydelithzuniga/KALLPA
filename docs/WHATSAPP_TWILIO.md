# WhatsApp HOY con Twilio (sin verificar el negocio en Meta)

Meta bloquea la cuenta de WhatsApp hasta verificar el negocio (RUC + documentos, 2–14 días).
El **Sandbox de Twilio** funciona en minutos y Kallpa ya lo soporta (`WHATSAPP_PROVIDER=twilio`).

## 1. Publica la app con HTTPS (Render) — ver GUIA_COMPLETA.md, fases 2 y 3
Al final tendrás una dirección tipo `https://kallpa-xxxx.onrender.com`.

## 2. Crea tu cuenta de Twilio (5 min)
1. Entra a **https://www.twilio.com/try-twilio** → regístrate (correo + verifica tu celular). Es gratis, con crédito de prueba.
2. En la consola (**console.twilio.com**), en **Account Info**, copia:
   - **Account SID** (empieza con `AC…`) → `TWILIO_ACCOUNT_SID`
   - **Auth Token** (clic en «Show») → `TWILIO_AUTH_TOKEN`
3. Menú **Messaging → Try it out → Send a WhatsApp message**. Verás:
   - el número del Sandbox: **+1 415 523 8886**
   - una frase tipo **`join palabra-palabra`** → `TWILIO_JOIN_CODE`
4. Desde tu celular manda esa frase (`join palabra-palabra`) al +1 415 523 8886. Twilio responde que ya estás conectada.

## 3. Conecta Twilio con Kallpa
En la misma página de Twilio → pestaña **Sandbox settings**:
- **When a message comes in:** `https://kallpa-xxxx.onrender.com/webhook/twilio` · método **POST**
- **Save**.

## 4. Variables en Render (Environment)
```
WHATSAPP_ENABLED=true
WHATSAPP_PROVIDER=twilio
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
TWILIO_JOIN_CODE=join palabra-palabra
TWILIO_WHATSAPP_FROM=+14155238886
APP_BASE_URL=https://kallpa-xxxx.onrender.com
```
Para que entienda **audios** de WhatsApp en Render, activa el agente (clave gratis en aistudio.google.com):
```
AGENT_ENABLED=true
GEMINI_API_KEY=...
```
Guarda. Revisa `https://kallpa-xxxx.onrender.com/api/health` → `"whatsapp": {"connected": true, "provider": "twilio", ...}`.

## 5. Vincula y prueba
1. App → **Más → Ajustes → WhatsApp** → «Tu número» = 51 + tu celular → **Guardar**.
2. **Inicio → 🟢 Abrir mi WhatsApp** → escribe «vendí 3 soles de tomate en efectivo» → responde «✓ S/ 3 tomate · efectivo» y aparece en la app.
3. Un número que no está vinculado empieza la conversación de bienvenida y crea su propio negocio.

## Para la presentación
- Cada celular (tuyo, del equipo y del jurado) debe mandar **una vez** `join palabra-palabra`.
  En la app hay un enlace «¿Primera vez? Activa tu WhatsApp con Kallpa» que lo prepara.
- La conexión del Sandbox dura **72 horas**: el día de la demo vuelve a mandar el `join …` antes de empezar.
- La cuenta de prueba tiene un límite diario de mensajes (unos 50): suficiente para la demo.
- Abre la URL de Render 2 minutos antes (el plan gratis se duerme) o deja cron-job.org llamando cada hora.

## Problemas comunes
| Síntoma | Solución |
|---|---|
| Twilio dice «You are not connected to the sandbox» | Manda otra vez `join palabra-palabra`. |
| No responde nada | Render → Logs. Revisa que la URL del Sandbox termine en `/webhook/twilio` y sea POST. |
| Logs: «Firma de Twilio inválida» (401) | `APP_BASE_URL` debe ser exactamente la URL de Render (https, sin «/» al final). Último recurso: `TWILIO_VALIDATE_SIGNATURE=false`. |
| «No pude escuchar bien tu audio» | Activa `AGENT_ENABLED=true` + `GEMINI_API_KEY`. |

Cuando Meta verifique tu negocio, cambia `WHATSAPP_PROVIDER=meta` y pon las variables de Meta (CONECTAR_WHATSAPP.md). El resto no cambia.
