# Kallpa — asistente financiero por voz para microemprendedoras

MVP para la hackathon BCP. La emprendedora **dicta** lo que pasó en su negocio («vendí tres polos por cincuenta soles en efectivo»), el asistente lo entiende, pregunta solo lo que falta (una pregunta por turno), pide confirmación y lo registra. Desde la app ve su caja, su mercadería, sus metas y descarga un **reporte de ingresos y capacidad de pago** para presentar a BCP o a una caja.

- **Backend**: Python 3.12 + FastAPI + Pydantic + SQLAlchemy 2 + SQLite (importes en céntimos enteros). Reglas propias en Python: interpretan el dictado, calculan descuentos, caja, inventario, metas, conciliación y reporte. **Sin IA para las operaciones diarias.**
- **App**: React + TypeScript + Vite como **PWA** instalable (service worker + IndexedDB para audios pendientes sin señal). Se puede empaquetar como **APK Android** con Capacitor.
- **Voz**: MediaRecorder en la app → **faster-whisper** (`base`, CPU, int8) en el servidor. Respaldo: reconocimiento de voz del navegador. Las respuestas se leen en voz alta.
- **Gemini**: una sola solicitud por negocio y solo con la descripción del rubro, para proponer la estructura inicial. Si no hay clave o falla → plantillas locales (reventa, comida preparada, servicios).
- **WhatsApp Cloud API** (Meta): mismo motor de conversación. Si no hay credenciales, el chat web es el canal y WhatsApp aparece «pendiente de conectar».

## Requisitos
- Python 3.12+ y Node.js 18+ (probado con Node 22)

## 1. Backend
```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env            # opcional: ninguna clave es obligatoria
python scripts/download_model.py   # descarga el modelo de voz (una vez, ~140 MB) antes de la demo
uvicorn app.main:app --host 0.0.0.0 --port 8000
```
Al iniciar carga **datos de demostración** (dos negocios ficticios: «Polos Rosita» – reventa y «Cocina de Doña Carmen» – comida). Para empezar en blanco usa `SEED_DEMO=false`.

Pruebas (casos de aceptación):
```bash
cd backend && python -m pytest -q
```

## 2. App (desarrollo)
```bash
cd frontend
npm install
npm run dev        # http://localhost:5173  (redirige /api al backend :8000)
```

## 3. Demo en un solo servidor (recomendado para presentar)
```bash
cd frontend && npm install && npm run build
cd ../backend && uvicorn app.main:app --host 0.0.0.0 --port 8000
```
El backend sirve la app compilada en `http://localhost:8000`. En la computadora, `localhost` permite usar el micrófono.

**En el celular**, el micrófono y la instalación de la PWA requieren HTTPS. Expón el puerto con un túnel, por ejemplo:
```bash
cloudflared tunnel --url http://localhost:8000
```
Abre la URL `https://…` en Chrome del celular → menú ⋮ → **Agregar a pantalla de inicio**. Queda como app; tras la primera carga abre sin señal y guarda los audios como «Pendiente de enviar».

## 4. APK Android (Capacitor)
Requiere Android Studio.
```bash
cd frontend
npm install
npm run android:init     # build + agrega plataforma android + permisos de micrófono
npm run android:open     # abre Android Studio → Run / Build APK
```
En la app: **Más → Ajustes → Servidor** coloca la URL del backend (por ejemplo la del túnel HTTPS o `http://IP-de-tu-PC:8000` en la misma red Wi-Fi). Tras cambios: `npm run android:sync`.

## Recorrido de demo (5 min)
1. **Inicio** → «Empezar mi negocio» → «Cuéntame qué vendes y cómo te pagan» por voz → revisa la propuesta → Sí, guardar. (O usa una plantilla.)
2. O entra a **Polos Rosita** (demo) y ve el panel: ¿Cuánto cobré? ¿Cuánto tengo? ¿Cuánto puedo usar para reponer? Flujo de caja 30 días, margen por producto, punto de equilibrio, rotación, mejores días, consejos.
3. **Dictar** (micrófono): «Vendí tres polos por cincuenta soles en efectivo» → «Tres polos básicos, S/ 50 en efectivo, con S/ 10 de descuento. ¿Lo guardo?» → «sí».
4. «Compré una docena de polos por 144 en total y pagué por Yape» → 12 unidades, S/ 12 c/u.
5. Activa modo avión, graba un audio → queda **Pendiente de enviar** → vuelve la señal → se procesa una sola vez.
6. «Conté 17 polos» → diferencia y qué revisar (Mercadería → Ajustar o Dejar pendiente).
7. «¿Qué es eso del flujo de caja?» → explicación con sus propios números.
8. **Metas**: «quiero juntar 1500 para una congeladora en diciembre».
9. **Más → Reporte para el banco** → pregunta mensual de envío al BCP (simulado) → Descargar PDF.

## Frases que entiende (ejemplos)
| Dicta | Registra |
|---|---|
| vendí 3 polos a 25 por Yape | venta (pregunta total/unidad si es ambiguo) |
| vendí 2 polos a la señora Juana, me pagó 30 y me debe 10 | venta con fiado parcial |
| Juana me pagó 10 del fiado | cobro vinculado a la venta |
| compré mercadería por 144 | compra con unidades pendientes |
| pagué la luz 80 / gasté 15 en pasajes | gasto del negocio (fijo / variable) |
| me saqué 100 para la casa | retiro personal (no es gasto del negocio) |
| puse 200 de mi bolsillo | aporte (no es venta) |
| pasé 100 de Yape a efectivo | traslado (no cambia ventas) |
| pagué la cuota del préstamo | pago de deuda |
| mi polo cuesta 20 y tengo 10 en stock | catálogo (pregunta si 20 es precio o costo) |
| conté 17 polos / tengo 300 en efectivo | conteo y conciliación |
| empiezo con 200 en efectivo y 150 en Yape | saldo inicial |
| corrige: eran dos polos / anula la última | corrección con historial / anulación |
| resumen · ¿cuánto tengo? · consejos · fiados · ¿qué es el margen? | respuestas con sus datos |

## Seguridad e idempotencia
- Cada mensaje tiene `message_id` y cada borrador un `op_id` único: reintentos de audio, webhooks repetidos de Meta o doble «sí» no duplican efectos.
- Caja e inventario se escriben en la misma transacción (líneas `cash_entries` / `stock_entries`). Las correcciones guardan la versión anterior en `movement_revisions`.
- Webhook de WhatsApp: verificación `hub.verify_token` y firma `X-Hub-Signature-256` con `WHATSAPP_APP_SECRET`. Credenciales solo en variables de entorno del servidor.

## WhatsApp (opcional)
1. Crea una app en Meta for Developers con WhatsApp Cloud API y un número de prueba.
2. Completa en `.env`: `WHATSAPP_ENABLED=true`, `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_APP_SECRET`, `WHATSAPP_VERIFY_TOKEN`.
3. Webhook: `https://TU-URL/webhook/whatsapp` (suscribe `messages`). Mensajes de texto y audios usan el mismo flujo; el resumen diario se envía con `POST /api/businesses/{id}/whatsapp/daily-summary`.

## Fuera del MVP
Scoring crediticio, aprobación de préstamos y conexiones bancarias reales. El envío al BCP es **simulado** (se registra la autorización mensual). Los datos de demostración son ficticios y se marcan como tales en el reporte.

## Estructura
```
backend/app/  nlu.py (dictado→borrador) · conversation.py (aclaración/confirmación) · ledger.py (caja+stock)
              metrics.py (indicadores) · reconcile.py (cruces) · report.py (reporte banco) · setup.py/gemini.py/templates.py
              transcribe.py (faster-whisper) · whatsapp.py · seed.py (demo) · main.py (API)
backend/tests/ casos de aceptación (pytest)
frontend/src/  pages: Onboarding, Chat, Home, Stock, Goals, Report, More · lib: api, outbox (IndexedDB), voice
```
