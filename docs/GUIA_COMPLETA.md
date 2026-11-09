# Guía completa: de cero a Kallpa funcionando con WhatsApp

Tiempo aproximado: 1 a 2 horas la primera vez. Hazlo en este orden.

---------------------------------------------------------------------------------------------------
## FASE 0 · Lo que necesitas tener
- Una computadora (Windows, Mac o Linux) con internet.
- Una cuenta de **GitHub** (github.com) — gratis.
- Una cuenta de **Facebook** para entrar a **Meta for Developers** (developers.facebook.com) — gratis.
- Una cuenta en **Render** (render.com) — gratis (puedes entrar con tu GitHub).
- Tu celular con WhatsApp.
- (Opcional) Una clave de **Gemini** en aistudio.google.com — gratis, para el agente de IA.

---------------------------------------------------------------------------------------------------
## FASE 1 · Probar la app en tu computadora (15 min)
1. Instala **Python 3.12** (python.org; en Windows marca «Add Python to PATH») y **Node.js 20 LTS** (nodejs.org).
2. Descomprime `kallpa-asistente-bcp.zip`. Abre una terminal (Windows: «Símbolo del sistema» o PowerShell) en la carpeta `kallpa`.
3. Construye la app:
   ```
   cd frontend
   npm install
   npm run build
   cd ..
   ```
4. Instala y arranca el servidor:
   ```
   cd backend
   python -m venv .venv
   .venv\Scripts\activate          (Windows)   |   source .venv/bin/activate   (Mac/Linux)
   pip install -r requirements-dev.txt
   copy .env.example .env          (Windows)   |   cp .env.example .env        (Mac/Linux)
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```
5. Abre **http://localhost:8000** en el navegador. Debe aparecer Kallpa con los negocios de ejemplo.
6. (Opcional) Voz en el servidor sin IA: `python scripts/download_model.py` (descarga ~140 MB, una vez).
7. (Opcional) Pruebas: `python -m pytest -q` → deben pasar todas.

---------------------------------------------------------------------------------------------------
## FASE 2 · Subir el código a GitHub (10 min)
Render publica la app desde GitHub.
1. En github.com → **New repository** → nombre `kallpa` → Create.
2. En la página del repositorio: **uploading an existing file** → arrastra TODO el contenido de la carpeta `kallpa`
   (sin `node_modules`, `.venv`, `dist` ni `kallpa.db`) → **Commit changes**.
   (Si usas git: `git init`, `git add .`, `git commit -m "Kallpa"`, `git remote add origin …`, `git push -u origin main`.)

---------------------------------------------------------------------------------------------------
## FASE 3 · Publicar la app en internet con Render (15 min)
1. Entra a **render.com** → **New +** → **Blueprint** → elige tu repositorio `kallpa`. Render lee `render.yaml`.
2. Te pedirá valores para las variables marcadas; por ahora pon algo provisional (puedes cambiarlas después en
   **Environment**). Clic en **Apply**. Espera que termine el build (5–10 min).
3. Render te da una dirección tipo **https://kallpa-xxxx.onrender.com**. Ábrela: es tu app, ya con HTTPS.
   - En el celular: ábrela en Chrome → menú ⋮ → **Agregar a pantalla de inicio** → queda como app.
4. Ve a **Environment** y pon `APP_BASE_URL` = esa dirección (sin «/» al final). Guarda (se reinicia sola).

Notas del plan gratis: se «duerme» tras 15 min sin uso (la primera visita tarda ~1 min en despertar) y los datos
(SQLite) se borran al reiniciar. Para algo permanente: plan pagado con disco, o una base PostgreSQL.

Alternativa rápida para un solo día (sin Render): con la Fase 1 corriendo, en otra terminal
`cloudflared tunnel --url http://localhost:8000` (instala cloudflared desde developers.cloudflare.com) y usa la
dirección https que te da. Mientras tu compu esté prendida, funciona.

---------------------------------------------------------------------------------------------------
## FASE 4 · Crear el número de WhatsApp de Kallpa en Meta (20 min)
> ⚠️ Meta pide **verificar el negocio** (RUC + documentos, 2–14 días) antes de enviar mensajes (error 131031).
> Si es urgente, usa **Twilio** en su lugar: [`WHATSAPP_TWILIO.md`](WHATSAPP_TWILIO.md) (funciona en minutos).

1. Entra a **developers.facebook.com** → **Mis apps** → **Crear app** → caso de uso «Otro» → tipo **Business** → nombre «Kallpa».
2. En el panel de la app → **Agregar producto** → **WhatsApp** → **Configurar** (crea o elige una cuenta de WhatsApp Business).
3. Ve a **WhatsApp → Configuración de la API** (API Setup). Ahí copia:
   - **Token de acceso temporal** → será `WHATSAPP_TOKEN` (dura 24 h; ver paso 6).
   - **Identificador del número de teléfono** (Phone number ID) → `WHATSAPP_PHONE_NUMBER_ID`.
   - El **número de prueba** que te asigna Meta (ej. +1 555 …) → `WHATSAPP_DISPLAY_NUMBER` (solo dígitos: 1555…).
4. En la misma pantalla, en **«Para» / To** → **Administrar lista de números** → agrega TU celular (+51…). Llega un código
   por WhatsApp; ingrésalo. (Puedes agregar hasta 5 celulares de prueba: los de tu equipo y el jurado.)
5. **Configuración de la app → Básica** → **Clave secreta de la app** → Mostrar → `WHATSAPP_APP_SECRET`.
6. Token que no vence (recomendado para la presentación): **business.facebook.com → Configuración del negocio →
   Usuarios del sistema → Agregar** (rol Administrador) → **Generar token** → elige la app Kallpa → permisos
   `whatsapp_business_messaging` y `whatsapp_business_management` → copia el token → reemplaza `WHATSAPP_TOKEN`.
   Luego en **Cuentas → Cuentas de WhatsApp** asigna ese usuario del sistema a tu cuenta de WhatsApp.

---------------------------------------------------------------------------------------------------
## FASE 5 · Poner las claves en Render (5 min)
En Render → tu servicio → **Environment** → completa:
```
WHATSAPP_ENABLED=true
WHATSAPP_TOKEN=(paso 4.6)
WHATSAPP_PHONE_NUMBER_ID=(paso 4.3)
WHATSAPP_APP_SECRET=(paso 4.5)
WHATSAPP_VERIFY_TOKEN=kallpa-2026          ← una palabra que tú inventas
WHATSAPP_DISPLAY_NUMBER=1555xxxxxxx        ← número de prueba de Meta, solo dígitos
APP_BASE_URL=https://kallpa-xxxx.onrender.com
```
Para el agente de IA (Women2, entiende texto y audio con Gemini) agrega:
```
AGENT_ENABLED=true
GEMINI_API_KEY=(de aistudio.google.com → Get API key)
AGENT_MODEL=(el modelo Gemini que tengas disponible, ej. el «flash» más reciente)
```
Guarda: el servicio se reinicia. Revisa **https://tu-url/api/health**: `whatsapp.connected` debe decir `true`.

---------------------------------------------------------------------------------------------------
## FASE 6 · Conectar el webhook (5 min)
Meta → tu app → **WhatsApp → Configuración** (Configuration) → **Webhook → Editar**:
- **URL de devolución de llamada:** `https://kallpa-xxxx.onrender.com/webhook/whatsapp`
- **Token de verificación:** `kallpa-2026` (el mismo de `WHATSAPP_VERIFY_TOKEN`)
- **Verificar y guardar.** (Si falla: la app en Render debe estar despierta; abre la URL antes y vuelve a intentar.)
- En **Campos del webhook** → **Administrar** → **messages** → **Suscribirse**.

---------------------------------------------------------------------------------------------------
## FASE 7 · Vincular tu WhatsApp con tu negocio y probar (10 min)
1. Abre tu app (la dirección de Render) → entra a tu negocio (o crea uno con «Aquí en la app»).
2. **Más → Ajustes → WhatsApp**: «Número de Kallpa» (aparece solo) y **«Tu número»** (51 + tu celular) → **Guardar**.
3. En **Inicio** el botón ahora dice **«🟢 Abrir mi WhatsApp»** → tócalo: se abre tu WhatsApp en el chat con Kallpa.
4. Escribe o manda un audio: «vendí 3 soles de tomate y un kilo de papa en efectivo».
   Debes recibir «✓ S/ 3 tomate, S/ 2.50 papa (1 kg) · efectivo» y verlo en la app (Inicio e Historial).
5. Si no responde: Render → **Logs**; Meta → WhatsApp → Configuración (webhook verificado y suscrito a *messages*);
   y que tu celular esté en la lista de números de prueba.

Si escribes desde un número que no está vinculado, Kallpa empieza la conversación de bienvenida (nombre, qué vendes,
cómo vendes, precios, cuánto te queda…) y crea un negocio nuevo para ese número.

---------------------------------------------------------------------------------------------------
## FASE 8 · Resúmenes y avisos automáticos (10 min)
Kallpa revisa cada hora si toca enviar algo (máx. 2 mensajes al día). Programa esa revisión:
1. Entra a **cron-job.org** (gratis) → **Create cronjob**.
2. URL: `https://kallpa-xxxx.onrender.com/api/notifications/run-all` · Método: **POST** · Frecuencia: **cada hora**.
3. Guarda. (Esto además mantiene despierta la app en Render.)

Para que Kallpa pueda escribir primero (fuera de las 24 h desde el último mensaje de ella), Meta exige una plantilla:
1. business.facebook.com → **WhatsApp Manager → Plantillas de mensajes → Crear plantilla**.
2. Categoría **Utilidad**, nombre `resumen_kallpa`, idioma Español, cuerpo: `Tu resumen de Kallpa: {{1}}`.
3. Cuando esté **aprobada**, en Render agrega `WHATSAPP_TEMPLATE_RESUMEN=resumen_kallpa`.

---------------------------------------------------------------------------------------------------
## FASE 9 · (Opcional) APK de Android
Necesitas Android Studio. En la carpeta `frontend`:
```
npm run android:init
npm run android:open
```
En Android Studio: **Build → Build APK**. En la app instalada: Más → Ajustes → Servidor = tu dirección de Render.

---------------------------------------------------------------------------------------------------
## Antes de la presentación (checklist)
- [ ] La app abre en el celular desde la dirección de Render (y está «Agregada a inicio»).
- [ ] Token permanente de Meta puesto (el temporal vence en 24 h).
- [ ] Los celulares del equipo/jurado están en la lista de números de prueba de Meta.
- [ ] «Abrir mi WhatsApp» abre el chat y una venta por audio aparece en la app.
- [ ] cron-job.org activo (despierta la app y envía resúmenes).
- [ ] Plan B: el link de demostración de claude.ai funciona sin servidor (sin WhatsApp real).

## Lo que es simulado en el MVP
- Verificación de Yape (Yape no tiene API pública): botón «Verificar con Yape (simulado)».
- Envío del informe al BCP: se registra la autorización mensual; no hay conexión con el banco.
- No hay usuarios/contraseña: no uses datos reales sensibles sin agregar inicio de sesión.
