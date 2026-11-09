# WhatsApp real y GRATIS para la demo: el puente (carpeta `bridge/`)

Meta pide verificar el negocio y Twilio pide recargar saldo. El **puente** conecta Kallpa con un WhatsApp
normal vinculado por QR (igual que WhatsApp Web). Quien le escribe a ese número conversa con Kallpa:
texto, audios, respuestas, resúmenes y avisos.

> ⚠️ No es la API oficial de WhatsApp. Sirve para un prototipo. Usa un **chip aparte** (no tu número
> personal): WhatsApp podría bloquear ese número. Para producción: Meta Cloud API con negocio verificado.

## ¿Con mi número personal o con un chip aparte?  (archivo `bridge/config.txt`)
| Modo | Configuración | Cómo se usa |
|---|---|---|
| **Solo yo** (tu número personal) | `SOLO_YO=si` · en `backend/.env`: `WHATSAPP_DISPLAY_NUMBER=` **tu** número | Escribes y mandas audios en tu chat **«Tú» (mensajes para ti mismo)**. Kallpa responde solo ahí. Tus contactos no reciben nada y tu WhatsApp sigue normal. |
| **Número de Kallpa** (chip aparte) | `SOLO_YO=no` · `WHATSAPP_DISPLAY_NUMBER=` número del chip | Cualquiera (tú, el jurado) le escribe a ese número. Con `PERMITIDOS=519…,519…` solo responde a esos. |

Para la demo con el jurado escribiendo desde sus celulares hace falta el chip aparte. Si solo tú vas a mostrarlo
en tu celular, «solo yo» basta.

## Lo que necesitas
- Modo «solo yo»: solo tu celular. Modo número de Kallpa: un **celular con un chip aparte** que tenga WhatsApp (puede ser un celular viejo o uno con doble chip
  usando WhatsApp Business para el segundo número). Este será **el número de Kallpa**.
- Tu laptop con **Node.js 20** y **Python 3.12** (los mismos de la guía).
- Tu celular personal para escribirle a Kallpa.

## Opción 1 · Todo en tu laptop (lo más rápido, recomendado para mañana)

### 1. Servidor de Kallpa
En `backend/.env` agrega (o cambia):
```
WHATSAPP_ENABLED=true
WHATSAPP_PROVIDER=bridge
BRIDGE_SECRET=kallpa-2026
WHATSAPP_DISPLAY_NUMBER=519XXXXXXXX
```
(`WHATSAPP_DISPLAY_NUMBER` = 51 + el número del chip de Kallpa, solo dígitos.)

Arranca el servidor (como en la Fase 1 de la guía):
```
cd backend
.venv\Scripts\activate
uvicorn app.main:app --host 0.0.0.0 --port 8000
```
Para que entienda **audios** en tu laptop: `python scripts/download_model.py` (una vez), o activa el agente con
`AGENT_ENABLED=true` y `GEMINI_API_KEY=...`.

### 2. Puente (otra terminal)
```
cd bridge
npm install
npm start
```
Aparece un **QR** en la terminal.
En el celular del **chip de Kallpa**: WhatsApp → ⋮ (o Configuración) → **Dispositivos vinculados** →
**Vincular un dispositivo** → escanea el QR. Verás: `✅ Conectado como 519…`.

(Si el QR se ve deformado, agranda la ventana de la terminal o reduce el zoom con Ctrl + −.)

### 3. Prueba
1. Abre **http://localhost:8000** → tu negocio → **Más → Ajustes → WhatsApp** → «Tu número» = 51 + tu celular
   personal → **Guardar**.
2. Desde tu celular personal escríbele al número de Kallpa: «vendí 3 soles de tomate en efectivo».
   Responde «✓ S/ 3 tomate · efectivo» y lo ves en la app. También funciona con audio.
3. Un número no vinculado (ej. el del jurado) empieza la conversación de bienvenida y crea su propio negocio.

La sesión queda guardada en `bridge/sesion-whatsapp`: la próxima vez `npm start` ya no pide QR.

### Ver la app en el celular (opcional)
Con el servidor prendido, en otra terminal: `cloudflared tunnel --url http://localhost:8000` y abre en el
celular la dirección https que te da. O conecta el celular al mismo WiFi y abre `http://IP-de-tu-laptop:8000`.

## Opción 2 · Servidor en Render + puente en tu laptop
1. En Render → Environment: `WHATSAPP_ENABLED=true`, `WHATSAPP_PROVIDER=bridge`, `BRIDGE_SECRET=kallpa-2026`,
   `WHATSAPP_DISPLAY_NUMBER=519…`, `APP_BASE_URL=https://kallpa-xxxx.onrender.com`.
2. En `bridge/config.txt` cambia `KALLPA_URL=https://kallpa-xxxx.onrender.com`.
3. `npm start` en la carpeta `bridge` y escanea el QR. El puente consulta al servidor cada 5 s (eso además
   evita que Render se duerma).

## Durante la demo
- La laptop con el puente debe estar **prendida y con internet** (el celular del chip también, con batería).
- En la terminal del puente ves cada mensaje que entra: `← 519…: vendí 3 soles de tomate`.
- Los resúmenes y avisos automáticos salen por el mismo número (botones en **Más → Mensajes automáticos**).

## Problemas comunes
| Síntoma | Solución |
|---|---|
| `⚠️ No encuentro el servidor de Kallpa` | Prende el servidor (paso 1) y revisa `KALLPA_URL` en `bridge/config.txt`. |
| `⚠️ El servidor no tiene … WHATSAPP_PROVIDER=bridge` | Revisa `backend/.env` y reinicia `uvicorn`. |
| No sale el QR / «Reconectando…» sin parar | Revisa el internet; cierra y vuelve a `npm start`. |
| «Se cerró la sesión» | Borra la carpeta `bridge/sesion-whatsapp` y vuelve a escanear. |
| Responde «No pude escuchar bien tu audio» | Descarga el modelo de voz o activa el agente con Gemini (paso 1). |
| Kallpa responde «está despertando…» | El servidor en Render estaba dormido: vuelve a enviar en 1 minuto. |
