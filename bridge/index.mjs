// Puente WhatsApp ⇄ Kallpa (gratis, para prototipos).
// Vincula un WhatsApp escaneando un QR (como WhatsApp Web). Cada mensaje que recibe ese número
// se manda a Kallpa (/webhook/bridge) y la respuesta vuelve al mismo chat.
// ⚠️ No es la API oficial de WhatsApp: usa un chip aparte, nunca tu número personal.
import makeWASocket, { DisconnectReason, downloadMediaMessage, fetchLatestBaileysVersion, useMultiFileAuthState } from '@whiskeysockets/baileys'
import pino from 'pino'
import qrcode from 'qrcode-terminal'

import { existsSync, readFileSync } from 'node:fs'

// Configuración: archivo «config.txt» junto a este script (KALLPA_URL=…, BRIDGE_SECRET=…) o variables de entorno.
if (existsSync(new URL('./config.txt', import.meta.url))) {
  for (const line of readFileSync(new URL('./config.txt', import.meta.url), 'utf8').split(/\r?\n/)) {
    const mm = line.match(/^\s*([A-Z_]+)\s*=\s*(.*?)\s*$/)
    if (mm && !process.env[mm[1]]) process.env[mm[1]] = mm[2]
  }
}
const KALLPA_URL = (process.env.KALLPA_URL || 'http://127.0.0.1:8000').replace(/\/$/, '')
const SECRET = process.env.BRIDGE_SECRET || ''
const POLL_MS = Number(process.env.POLL_MS || 5000)
// SOLO_YO=si: usas tu número personal y hablas con Kallpa en tu chat «Tú» (mensajes para ti). Ignora a todos los demás.
const SOLO_YO = /^(si|sí|true|1)$/i.test(process.env.SOLO_YO || '')
// PERMITIDOS=51911111111,51922222222 (opcional): solo responde a esos números (además de ti).
const PERMITIDOS = new Set((process.env.PERMITIDOS || '').split(',').map((x) => x.replace(/\D/g, '')).filter(Boolean))
const sentIds = new Set()   // lo que envía el puente (para no responderse a sí mismo en el chat «Tú»)
if (!SECRET) { console.error('Falta BRIDGE_SECRET en config.txt (la misma clave que pusiste en el servidor).'); process.exit(1) }

const logger = pino({ level: process.env.LOG_LEVEL || 'silent' })
const jidByPhone = new Map()   // número -> chat original (por si WhatsApp usa identificadores @lid)
let sock = null

const digits = (s) => String(s || '').split('@')[0].split(':')[0].replace(/\D/g, '')

async function api(path, body) {
  const r = await fetch(KALLPA_URL + path, {
    method: body ? 'POST' : 'GET',
    headers: { 'Content-Type': 'application/json', 'X-Bridge-Secret': SECRET },
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`)
  return r.json()
}

async function deliver(items) {
  for (const it of items || []) {
    const jid = jidByPhone.get(it.to) || `${it.to}@s.whatsapp.net`
    try {
      let sent = null
      if (it.audio_url) sent = await sock.sendMessage(jid, { audio: { url: it.audio_url }, mimetype: 'audio/mpeg' })
      else if (it.text) sent = await sock.sendMessage(jid, { text: it.text })
      if (sent?.key?.id) sentIds.add(sent.key.id)
    } catch (e) { console.error('No se pudo enviar a', it.to, e.message) }
  }
}

function textOf(m) {
  return m?.conversation || m?.extendedTextMessage?.text || m?.buttonsResponseMessage?.selectedDisplayText ||
    m?.listResponseMessage?.title || m?.ephemeralMessage?.message?.conversation ||
    m?.ephemeralMessage?.message?.extendedTextMessage?.text || null
}

async function onMessage(msg) {
  const k = msg.key || {}
  if (!msg.message || sentIds.has(k.id)) return
  const chat = k.remoteJid || ''
  if (chat.endsWith('@g.us') || chat === 'status@broadcast' || chat.endsWith('@newsletter')) return
  const me = digits(sock.user?.id)
  const myLid = digits(sock.user?.lid)
  const isSelf = digits(chat) === me || (myLid && digits(chat) === myLid)
  if (k.fromMe && !isSelf) return                      // lo que tú escribes a otras personas: no se toca
  if (SOLO_YO && !isSelf) return                        // modo «solo yo»: nadie más recibe respuestas de Kallpa
  const ts = Number(msg.messageTimestamp || 0)
  if (ts && Date.now() / 1000 - ts > 300) return        // mensajes viejos (sincronización): se ignoran
  const pnJid = [k.remoteJidAlt, k.senderPn, chat].find((j) => j && j.endsWith('@s.whatsapp.net'))
  const phone = isSelf ? me : digits(pnJid || chat)
  if (PERMITIDOS.size && !isSelf && !PERMITIDOS.has(phone)) return
  jidByPhone.set(phone, chat)
  const m = msg.message.ephemeralMessage?.message || msg.message
  const body = { id: k.id, from: phone, text: textOf(m), timestamp: Number(msg.messageTimestamp || 0) || null }
  if (m.audioMessage) {
    try {
      const buf = await downloadMediaMessage(msg, 'buffer', {}, { logger, reuploadRequest: sock.updateMediaMessage })
      body.audio_b64 = buf.toString('base64')
      body.mime = (m.audioMessage.mimetype || 'audio/ogg').split(';')[0]
    } catch (e) { console.error('No se pudo bajar el audio:', e.message) }
  }
  if (!body.text && !body.audio_b64) return
  console.log(`← ${phone}: ${body.text || '[audio]'}`)
  try {
    await sock.sendPresenceUpdate('composing', chat).catch(() => {})
    const r = await api('/webhook/bridge', body)
    await deliver(r.outbox)
  } catch (e) {
    console.error('Kallpa no respondió:', e.message)
    await sock.sendMessage(chat, { text: 'Kallpa está despertando, vuelve a mandar tu mensaje en un minuto 🙏' }).catch(() => {})
  }
}

async function poll() {   // resúmenes y avisos automáticos que Kallpa quiere enviar
  if (sock?.user) {
    try { await deliver((await api('/webhook/bridge/outbox')).outbox) } catch (e) { /* servidor dormido: reintenta */ }
  }
  setTimeout(poll, POLL_MS)
}

async function start() {
  const { state, saveCreds } = await useMultiFileAuthState('sesion-whatsapp')
  const { version } = await fetchLatestBaileysVersion().catch(() => ({ version: undefined }))
  sock = makeWASocket({ auth: state, logger, version, browser: ['Kallpa', 'Chrome', '1.0'], markOnlineOnConnect: false })
  sock.ev.on('creds.update', saveCreds)
  sock.ev.on('connection.update', ({ connection, lastDisconnect, qr }) => {
    if (qr) {
      console.log('\nEscanea este QR con el celular de Kallpa: WhatsApp → ⋮ → Dispositivos vinculados → Vincular un dispositivo\n')
      qrcode.generate(qr, { small: true })
    }
    if (connection === 'open') {
      console.log(`\n✅ Conectado como ${digits(sock.user?.id)}. Kallpa: ${KALLPA_URL}`)
      console.log(SOLO_YO ? 'Modo «solo yo»: escribe en tu chat «Tú» (mensajes para ti). Nadie más recibe respuestas.\n'
        : PERMITIDOS.size ? `Solo responde a: ${[...PERMITIDOS].join(', ')}\n` : 'Responde a todos los que escriban a este número.\n')
    }
    if (connection === 'close') {
      const code = lastDisconnect?.error?.output?.statusCode
      if (code === DisconnectReason.loggedOut) {
        console.log('Se cerró la sesión. Borra la carpeta «sesion-whatsapp» y vuelve a ejecutar para escanear otro QR.')
        process.exit(1)
      }
      console.log('Reconectando…')
      setTimeout(start, 2000)
    }
  })
  sock.ev.on('messages.upsert', async ({ messages, type }) => {
    if (type !== 'notify' && type !== 'append') return
    for (const msg of messages) await onMessage(msg).catch((e) => console.error(e))
  })
}

console.log(`Kallpa · puente de WhatsApp\nServidor: ${KALLPA_URL}\nConectando con WhatsApp…`)
fetch(KALLPA_URL + '/api/health').then((r) => r.json()).then((h) => {
  if (h.whatsapp?.provider !== 'bridge' || !h.whatsapp?.connected) console.log('⚠️  El servidor no tiene WHATSAPP_ENABLED=true y WHATSAPP_PROVIDER=bridge con BRIDGE_SECRET.')
  else console.log('Servidor listo ✓')
}).catch(() => console.log('⚠️  No encuentro el servidor de Kallpa en ' + KALLPA_URL + ' (¿está prendido?)'))
start()
poll()
