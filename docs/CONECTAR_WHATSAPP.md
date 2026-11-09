# Conectar Kallpa con un WhatsApp real

Objetivo: la emprendedora toca **«Abrir mi WhatsApp»** en la app, se abre su WhatsApp en el chat con Kallpa,
y lo que escriba o mande por audio ahí se registra en la misma app (mismo agente, mismos datos).

```
Celular (WhatsApp) ──► Meta (WhatsApp Cloud API) ──► webhook HTTPS ──► backend Kallpa ──► misma base de datos ◄── app
                   ◄── respuesta (texto + audio) ◄────────────────────────────┘
```

> El link de demostración en claude.ai corre todo dentro del navegador: **no puede recibir mensajes de WhatsApp**.
> Para el WhatsApp real el backend debe estar en un servidor con internet (HTTPS).

## 1. Publicar el backend con HTTPS
Opción rápida para la presentación (desde tu computadora):
```bash
cd frontend && npm install && npm run build
cd ../backend && pip install -r requirements.txt && uvicorn app.main:app --host 0.0.0.0 --port 8000
cloudflared tunnel --url http://localhost:8000      # te da https://algo.trycloudflare.com
```
Opción estable: Render, Railway, Fly.io o un VPS (comando de inicio: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`).
La misma URL sirve la app (PWA) y el webhook.

## 2. Crear el número de WhatsApp en Meta
1. Entra a **developers.facebook.com** → *Crear app* → tipo **Business** → agrega el producto **WhatsApp**.
2. En **WhatsApp → Configuración de la API** verás:
   - un **número de prueba** de Meta (ese será el número de Kallpa),
   - el **Phone number ID**,
   - un **token temporal** (dura 24 h; para la demo crea un token permanente de *usuario del sistema* en el Business Manager).
3. En la misma pantalla, en **«Para»**, agrega tu celular (hasta 5 números de prueba). Te llega un código por WhatsApp.
4. **Configuración de la app → Básica** → copia la **Clave secreta de la app**.
5. Para usar un número propio (no el de prueba) hay que verificar el negocio en Meta y registrar un número que no esté
   en uso en la app de WhatsApp. Eso toma días; para la hackathon usa el número de prueba.

## 3. Variables en `backend/.env`
```
WHATSAPP_ENABLED=true
WHATSAPP_TOKEN=EAAG...                 # token de Meta
WHATSAPP_PHONE_NUMBER_ID=1234567890    # Phone number ID (no es el número)
WHATSAPP_APP_SECRET=abcd...            # clave secreta de la app (valida la firma del webhook)
WHATSAPP_VERIFY_TOKEN=kallpa-2026      # una palabra que inventas
WHATSAPP_DISPLAY_NUMBER=15551234567    # el número de Kallpa (el de prueba), solo dígitos
APP_BASE_URL=https://tu-url-publica    # para enviar las respuestas en audio
# Agente de IA (Women2) para entender texto y audio con Gemini (opcional; sin esto usa reglas + Whisper)
AGENT_ENABLED=true
GEMINI_API_KEY=...
# Para que Kallpa escriba primero (resúmenes de la noche, domingo, día 1) fuera de las 24 h:
WHATSAPP_TEMPLATE_RESUMEN=resumen_kallpa   # plantilla de utilidad aprobada con 1 parámetro {{1}}
```
Reinicia el backend.

## 4. Conectar el webhook
En Meta → **WhatsApp → Configuración → Webhook → Editar**:
- **URL de devolución de llamada:** `https://tu-url-publica/webhook/whatsapp`
- **Token de verificación:** el mismo `WHATSAPP_VERIFY_TOKEN`
- **Administrar → Suscribirse** al campo **messages**.

## 5. Vincular el WhatsApp de la emprendedora con su negocio
En la app: **Más → Ajustes → WhatsApp**
- **Número de WhatsApp de Kallpa:** el número de prueba de Meta (si ya pusiste `WHATSAPP_DISPLAY_NUMBER`, aparece solo).
- **Tu número de WhatsApp:** el celular de la emprendedora (ej. `51987654321`).
- **Guardar**. Desde ahí, los botones **«Abrir mi WhatsApp»** (Inicio y Dictar) abren su WhatsApp en el chat con Kallpa,
  y sus mensajes entran a ese mismo negocio. Si escribe un número que no está vinculado, Kallpa empieza la conversación
  de bienvenida y crea un negocio nuevo.

## 6. Probar
```bash
cd backend && python scripts/whatsapp_test.py --to 51987654321     # Kallpa te escribe
```
Luego, desde tu WhatsApp, manda al número de Kallpa: «vendí 3 soles de tomate y un kilo de papa en efectivo» (texto o audio).
Debes recibir «✓ S/ 3 tomate, S/ 2.50 papa (1 kg) · efectivo» y verlo en la app (Inicio e Historial).

## Problemas comunes
- **No llega nada al backend:** revisa que el webhook esté verificado y suscrito a *messages*, y que la URL sea HTTPS.
- **401 «Firma inválida»:** `WHATSAPP_APP_SECRET` no coincide con la clave secreta de la app.
- **El bot no responde:** token vencido (los temporales duran 24 h) o tu número no está en la lista de prueba.
- **Kallpa no puede escribir primero:** fuera de las 24 h Meta exige plantilla aprobada (`WHATSAPP_TEMPLATE_RESUMEN`).
