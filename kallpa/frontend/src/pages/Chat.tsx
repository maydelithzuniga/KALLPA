import { useCallback, useEffect, useRef, useState } from 'react'
import type { Ctx } from '../App'
import { ApiError, apiBase, fmtTime, get, send, uid } from '../lib/api'
import { outbox, type OutboxItem } from '../lib/outbox'
import { load, save } from '../lib/store'
import type { ChatResponse, Draft } from '../lib/types'
import { browserRecognizer, extFor, Recorder, speak } from '../lib/voice'
import { IconMic, IconMute, IconSend, IconSpeaker, IconStop } from '../components/icons'

type Msg = { id: string; role: 'user' | 'bot' | 'pending'; text: string; at: string; voice?: boolean; error?: string }

export default function Chat({ ctx }: { ctx: Ctx }) {
  const bid = ctx.business.id
  const [msgs, setMsgs] = useState<Msg[]>([])
  const [pending, setPending] = useState<OutboxItem[]>([])
  const [draft, setDraft] = useState<Draft | null>(null)
  const [quick, setQuick] = useState<string[]>([])
  const [text, setText] = useState('')
  const [recording, setRecording] = useState(false)
  const [busy, setBusy] = useState(false)
  const [tts, setTts] = useState<boolean>(() => load('kallpa.tts', true))
  const [lastUpdate, setLastUpdate] = useState<string | null>(() => load(`kallpa.lastUpdate.${bid}`, null))
  const rec = useRef<Recorder | null>(null)
  const flushing = useRef(false)
  const endRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const serverVoice = !!ctx.health?.transcription.installed && !!ctx.health?.transcription.model_on_disk

  const scroll = () => setTimeout(() => endRef.current?.scrollIntoView({ behavior: 'smooth' }), 30)

  useEffect(() => {
    get<{ id: number; role: 'user' | 'bot'; text: string; created_at: string; via_voice: boolean }[]>(`/api/businesses/${bid}/chat/history?limit=40`)
      .then((rows) => {
        const base: Msg[] = rows.map((r) => ({ id: String(r.id), role: r.role, text: r.text, at: r.created_at, voice: r.via_voice }))
        if (!base.length) base.push({ id: 'hello', role: 'bot', at: new Date().toISOString(), text: `¡Hola${ctx.business.owner_name ? ' ' + ctx.business.owner_name : ''}! Toca el micrófono y cuéntame qué vendiste o gastaste. Por ejemplo: «vendí tres polos por cincuenta soles en efectivo».` })
        setMsgs(base)
        save(`kallpa.chat.${bid}`, base.slice(-40))
        scroll()
      })
      .catch(() => { setMsgs(load<Msg[]>(`kallpa.chat.${bid}`, [])); scroll() })
    get<{ draft: Draft | null }>(`/api/businesses/${bid}/chat/pending`).then((r) => setDraft(r.draft)).catch(() => undefined)
    outbox.all().then((items) => setPending(items.filter((i) => i.businessId === bid)))
  }, [bid])

  const applyResponse = useCallback((item: OutboxItem, r: ChatResponse) => {
    const now = new Date().toISOString()
    setMsgs((m) => {
      const next = [...m]
      const userText = item.kind === 'audio' ? (r.transcript ? `🎙️ ${r.transcript}` : '🎙️ (audio)') : item.text ?? ''
      next.push({ id: item.id + '-u', role: 'user', text: userText, at: item.recordedAt, voice: item.kind === 'audio' })
      next.push({ id: item.id + '-b', role: 'bot', text: r.reply + (r.duplicate ? ' (ya estaba registrado)' : ''), at: now })
      save(`kallpa.chat.${bid}`, next.slice(-40))
      return next
    })
    setDraft(r.draft)
    setQuick(r.quick_replies ?? [])
    setLastUpdate(r.updated_at)
    save(`kallpa.lastUpdate.${bid}`, r.updated_at)
    if (tts) speak(r.reply)
    if (r.movement || r.count) ctx.refresh()
    scroll()
  }, [bid, tts, ctx])

  /** Envía la cola. Cada elemento lleva su message_id: el servidor nunca lo procesa dos veces. */
  const flush = useCallback(async () => {
    if (flushing.current || !navigator.onLine) return
    flushing.current = true
    setBusy(true)
    try {
      const items = (await outbox.all()).filter((i) => i.businessId === bid)
      for (const item of items) {
        try {
          let r: ChatResponse
          if (item.kind === 'audio' && item.blob) {
            const f = new FormData()
            f.append('audio', item.blob, 'audio' + extFor(item.mime || item.blob.type))
            f.append('message_id', item.id)
            f.append('recorded_at', item.recordedAt)
            if (item.opId) f.append('op_id', item.opId)
            const res = await fetch(apiBase() + `/api/businesses/${bid}/chat/audio`, { method: 'POST', body: f })
            if (!res.ok) throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail || res.statusText)
            r = await res.json()
          } else {
            r = await send<ChatResponse>(`/api/businesses/${bid}/chat`, { text: item.text, message_id: item.id, op_id: item.opId, recorded_at: item.recordedAt })
          }
          await outbox.remove(item.id)
          setPending((p) => p.filter((x) => x.id !== item.id))
          applyResponse(item, r)
        } catch (e) {
          if (e instanceof ApiError && e.status === 503) {
            item.attempts += 1
            item.lastError = 'No pude transcribir este audio en el servidor. Escríbelo o vuelve a intentar.'
            await outbox.put(item)
            setPending((p) => p.map((x) => (x.id === item.id ? { ...item } : x)))
            continue
          }
          if (e instanceof ApiError && e.status >= 400 && e.status < 500) {
            await outbox.remove(item.id)
            setPending((p) => p.filter((x) => x.id !== item.id))
            setMsgs((m) => [...m, { id: item.id + '-e', role: 'bot', text: `No pude registrar eso: ${e.message}`, at: new Date().toISOString() }])
            continue
          }
          break   // sin red: se reintenta luego
        }
      }
    } finally {
      flushing.current = false
      setBusy(false)
    }
  }, [bid, applyResponse])

  useEffect(() => {
    flush()
    const on = () => flush()
    window.addEventListener('online', on)
    document.addEventListener('visibilitychange', on)
    const t = setInterval(flush, 20000)
    return () => { window.removeEventListener('online', on); document.removeEventListener('visibilitychange', on); clearInterval(t) }
  }, [flush])

  async function enqueue(item: OutboxItem) {
    await outbox.put(item)
    setPending((p) => [...p, item])
    scroll()
    flush()
  }

  function sendText(t: string, opId?: string) {
    const clean = t.trim()
    if (!clean) return
    setText('')
    setQuick([])
    enqueue({ id: uid(), businessId: bid, kind: 'text', text: clean, opId, recordedAt: new Date().toISOString(), attempts: 0 })
  }

  async function toggleMic() {
    if (recording) {
      setRecording(false)
      if (rec.current) {
        const blob = await rec.current.stop()
        rec.current = null
        if (blob.size < 800) return
        enqueue({ id: uid(), businessId: bid, kind: 'audio', blob, mime: blob.type, opId: draft?.op_id && draft.missing === null ? draft.op_id : undefined,
          recordedAt: new Date().toISOString(), attempts: 0 })
      }
      return
    }
    window.speechSynthesis?.cancel()
    // Sin conexión o con transcripción en el servidor: graba el audio (queda pendiente si no hay señal)
    if ((serverVoice || !navigator.onLine) && Recorder.supported()) {
      try { rec.current = new Recorder(); await rec.current.start(); setRecording(true) }
      catch { ctx.toast('Necesito permiso para usar el micrófono.') }
      return
    }
    // Respaldo: reconocimiento del navegador
    const sr = browserRecognizer()
    if (!sr) {
      if (Recorder.supported()) {
        try { rec.current = new Recorder(); await rec.current.start(); setRecording(true) } catch { ctx.toast('Necesito permiso para usar el micrófono.') }
      } else ctx.toast('Tu celular no permite grabar aquí. Escríbelo.')
      return
    }
    setRecording(true)
    sr.onresult = (e) => sendText(e.results[0][0].transcript)
    sr.onerror = () => ctx.toast('No te escuché bien, intenta otra vez.')
    sr.onend = () => setRecording(false)
    sr.start()
  }

  async function discard(item: OutboxItem) {
    await outbox.remove(item.id)
    setPending((p) => p.filter((x) => x.id !== item.id))
  }

  const confirmLabel = draft?.action === 'consentimiento' ? 'Sí, envíalo' : draft?.action === 'anulacion' ? 'Sí, anular' : 'Sí, guardar'

  return (
    <div className="chat">
      <div className="status-line">
        <span className={`pill ${ctx.online ? 'good' : 'warn'}`}>{ctx.online ? 'En línea' : 'Sin conexión: guardo tus audios'}</span>
        <span className={`pill ${ctx.health?.whatsapp.connected ? 'good' : ''}`}>WhatsApp: {ctx.health?.whatsapp.status ?? 'pendiente de conectar'}</span>
        {lastUpdate && <span>Última actualización {fmtTime(lastUpdate)}</span>}
        <button className="iconbtn" style={{ width: 32, height: 32, marginLeft: 'auto' }} onClick={() => { setTts(!tts); save('kallpa.tts', !tts) }}
          aria-label={tts ? 'Silenciar respuestas' : 'Leer respuestas en voz alta'}>{tts ? <IconSpeaker /> : <IconMute />}</button>
      </div>
      <div className="msgs" aria-live="polite">
        {msgs.map((m) => (
          <div key={m.id} className={`msg ${m.role}`}>{m.text}<span className="meta">{fmtTime(m.at)}</span></div>
        ))}
        {pending.map((p) => (
          <div key={p.id} className="msg pending">
            {p.kind === 'audio' ? '🎙️ Audio' : p.text} · <b>Pendiente de enviar</b>
            <span className="meta">Grabado {fmtTime(p.recordedAt)}{p.attempts ? ` · ${p.attempts} intento(s)` : ''}</span>
            {p.lastError && <span className="meta">{p.lastError} <button className="btn sm ghost" onClick={() => discard(p)}>Borrar</button></span>}
          </div>
        ))}
        {busy && pending.length > 0 && ctx.online && <div className="faint">Enviando…</div>}
        <div ref={endRef} />
      </div>
      {draft && draft.status === 'abierto' && draft.missing === null && (
        <div className="draft no-print">
          <div className="faint">Pendiente de tu confirmación</div>
          <div className="actions">
            <button className="btn" onClick={() => sendText('sí', draft.op_id)}>{confirmLabel}</button>
            {draft.action === 'movimiento' && <button className="btn ghost" onClick={() => { setText('no, '); inputRef.current?.focus() }}>Corregir</button>}
            <button className="btn ghost" onClick={() => sendText(draft.action === 'consentimiento' ? 'no por ahora' : 'cancelar', draft.op_id)}>
              {draft.action === 'consentimiento' ? 'No por ahora' : 'Cancelar'}</button>
          </div>
        </div>
      )}
      {quick.length > 0 && !(draft && draft.missing === null) && (
        <div className="quick">{quick.map((q) => <button key={q} onClick={() => sendText(q)}>{q}</button>)}</div>
      )}
      <div className="composer">
        <textarea ref={inputRef} className="input" rows={1} value={text} placeholder="Escribe si no puedes grabar…"
          onChange={(e) => setText(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendText(text) } }} />
        {text.trim() ? (
          <button className="send" onClick={() => sendText(text)} aria-label="Enviar"><IconSend /></button>
        ) : (
          <button className={`mic ${recording ? 'rec' : ''}`} onClick={toggleMic} aria-label={recording ? 'Terminar y enviar' : 'Hablar'}>
            {recording ? <IconStop /> : <IconMic />}
          </button>
        )}
      </div>
    </div>
  )
}
