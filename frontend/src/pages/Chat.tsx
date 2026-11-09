import { useCallback, useEffect, useRef, useState } from 'react'
import type { Ctx } from '../App'
import { ApiError, apiBase, botNumber, fmtTime, get, send, uid, waLinkFor } from '../lib/api'
import { outbox, type OutboxItem } from '../lib/outbox'
import { load, save } from '../lib/store'
import type { ChatResponse, Draft, SetupProduct } from '../lib/types'
import { browserRecognizer, extFor, Recorder, speak } from '../lib/voice'
import { IconMic, IconMute, IconSend, IconSpeaker, IconStop } from '../components/icons'

type Msg = { id: string; role: 'user' | 'bot' | 'pending'; text: string; at: string; voice?: boolean; error?: string; aviso?: boolean; share?: { text: string; url: string; label: string } }

export default function Chat({ ctx }: { ctx: Ctx }) {
  const channel: 'web' | 'whatsapp' = ctx.sub === 'whatsapp' ? 'whatsapp' : 'web'
  const waLink = botNumber(ctx.health?.whatsapp.number) ? waLinkFor(botNumber(ctx.health?.whatsapp.number)) : null
  const bid = ctx.business.id
  const isSetup = ctx.business.setup_state !== 'listo'
  const helloSent = useRef(false)
  const [setup, setSetup] = useState<ChatResponse['setup'] | null>(null)
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
    get<{ id: number; role: 'user' | 'bot'; text: string; created_at: string; via_voice: boolean; channel: string }[]>(`/api/businesses/${bid}/chat/history?limit=40&channel=${channel}`)
      .then((rows) => {
        const base: Msg[] = rows.map((r) => ({ id: String(r.id), role: r.role, text: r.text, at: r.created_at, voice: r.via_voice, aviso: r.channel === 'aviso' }))
        if (!base.length && isSetup && !helloSent.current) { helloSent.current = true; setTimeout(() => sendText('Hola'), 50) }
        if (!base.length && !isSetup) base.push({ id: 'hello', role: 'bot', at: new Date().toISOString(), text: `¡Hola${ctx.business.owner_name ? ' ' + ctx.business.owner_name : ''}! Toca el micrófono y cuéntame qué vendiste o gastaste. Por ejemplo: «vendí tres polos por cincuenta soles en efectivo».` })
        setMsgs(base)
        save(`kallpa.chat.${bid}.${channel}`, base.slice(-40))
        scroll()
      })
      .catch(() => { setMsgs(load<Msg[]>(`kallpa.chat.${bid}.${channel}`, [])); scroll() })
    get<{ draft: Draft | null }>(`/api/businesses/${bid}/chat/pending?channel=${channel}`).then((r) => setDraft(r.draft)).catch(() => undefined)
    outbox.all().then((items) => setPending(items.filter((i) => i.businessId === bid && (i.channel ?? 'web') === channel)))
  }, [bid])

  const applyResponse = useCallback((item: OutboxItem, r: ChatResponse) => {
    if (r.setup) {
      setSetup(r.setup)
      if (r.setup.done) { ctx.toast('¡Tu negocio está listo!'); setTimeout(() => ctx.refresh(), 2500) }
    }
    const now = new Date().toISOString()
    setMsgs((m) => {
      const next = [...m]
      const userText = item.kind === 'audio' ? (r.transcript ? `🎙️ ${r.transcript}` : '🎙️ (audio)') : item.text ?? ''
      next.push({ id: item.id + '-u', role: 'user', text: userText, at: item.recordedAt, voice: item.kind === 'audio' })
      next.push({ id: item.id + '-b', role: 'bot', text: r.reply + (r.duplicate ? ' (ya estaba registrado)' : ''), at: now, share: r.share })
      save(`kallpa.chat.${bid}.${channel}`, next.slice(-40))
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
      const items = (await outbox.all()).filter((i) => i.businessId === bid && (i.channel ?? 'web') === channel)
      for (const item of items) {
        try {
          let r: ChatResponse
          if (item.kind === 'audio' && item.blob) {
            const f = new FormData()
            f.append('audio', item.blob, 'audio' + extFor(item.mime || item.blob.type))
            f.append('message_id', item.id)
            f.append('channel', item.channel ?? 'web')
            f.append('recorded_at', item.recordedAt)
            if (item.opId) f.append('op_id', item.opId)
            const res = await fetch(apiBase() + `/api/businesses/${bid}/chat/audio`, { method: 'POST', body: f })
            if (!res.ok) throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail || res.statusText)
            r = await res.json()
          } else {
            r = await send<ChatResponse>(`/api/businesses/${bid}/chat`, { text: item.text, message_id: item.id, op_id: item.opId, recorded_at: item.recordedAt, channel: item.channel ?? 'web' })
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

  const closeSent = useRef(false)
  useEffect(() => {
    if (ctx.sub === 'cierre' && !closeSent.current) { closeSent.current = true; sendText('Cerrar mi día') }
    if (ctx.sub === 'contar' && !closeSent.current) { closeSent.current = true; sendText('Quiero contar mi plata') }
  }, [ctx.sub]) // eslint-disable-line react-hooks/exhaustive-deps

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
    enqueue({ id: uid(), businessId: bid, channel, kind: 'text', text: clean, opId, recordedAt: new Date().toISOString(), attempts: 0 })
  }

  async function toggleMic() {
    if (recording) {
      setRecording(false)
      if (rec.current) {
        const blob = await rec.current.stop()
        rec.current = null
        if (blob.size < 800) return
        enqueue({ id: uid(), businessId: bid, channel, kind: 'audio', blob, mime: blob.type, opId: draft?.op_id && draft.missing === null ? draft.op_id : undefined,
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

  const unitTxt = (u: string | null) => ({ kg: 'kg', unidad: 'unid.', atado: 'atado', soles: 'de a sol', docena: 'docena', plato: 'plato' } as Record<string, string>)[u ?? ''] ?? (u ?? '')
  const productLine = (p: SetupProduct) => {
    const price = p.vende_por?.find((v) => v.precio_cents)?.precio_cents
    return `${p.name}${price ? ` S/ ${(price / 100).toLocaleString('es-PE')}/${unitTxt(p.base)}` : ''}`
  }
  const confirmLabel = draft?.action === 'consentimiento' ? 'Sí, envíalo' : draft?.action === 'anulacion' ? 'Sí, anular' : 'Sí, guardar'

  return (
    <div className={`chat ${channel === 'whatsapp' ? 'wa' : ''}`}>
      <div className="chat-top">
      {!isSetup && (
        <div className="seg" style={{ marginBottom: 8 }}>
          <button className={channel === 'web' ? 'on' : ''} onClick={() => ctx.go('chat')}>💬 Chat de la app</button>
          <button className={channel === 'whatsapp' ? 'on' : ''} onClick={() => ctx.go('chat', 'whatsapp')}>🟢 WhatsApp</button>
        </div>
      )}
      {channel === 'whatsapp' && (
        <div className="wa-head">
          <img src={`${import.meta.env.BASE_URL}icon.svg`} alt="" />
          <div style={{ flex: 1 }}><b>Kallpa</b><span>{waLink ? 'tu chat real está en WhatsApp' : 'vista de prueba · conecta el número en Más → Ajustes'}</span></div>
          {waLink && <a className="btn sm" href={waLink} target="_blank" rel="noreferrer">Abrir mi WhatsApp</a>}
        </div>
      )}
      </div>
      {isSetup && setup && (
        <div className="qcard" style={{ padding: '12px 16px', marginBottom: 8 }}>
          <div className="spread small"><b>Conociendo tu negocio</b><span className="faint">Paso {setup.step} de {setup.total}</span></div>
          <div className="bar" style={{ margin: '8px 0' }}><i style={{ width: `${(100 * setup.step) / setup.total}%` }} /></div>
          {setup.products.length > 0 && <div className="faint">Tu lista: {setup.products.map(productLine).join(' · ')}</div>}
        </div>
      )}
      <div className="status-line">
        {!ctx.online && <span className="pill warn">Sin conexión: guardo tus audios y los envío después</span>}
        {lastUpdate && <span>Última actualización {fmtTime(lastUpdate)}</span>}
        <button className="iconbtn" style={{ width: 32, height: 32, marginLeft: 'auto' }} onClick={() => { setTts(!tts); save('kallpa.tts', !tts) }}
          aria-label={tts ? 'Silenciar respuestas' : 'Leer respuestas en voz alta'}>{tts ? <IconSpeaker /> : <IconMute />}</button>
      </div>
      <div className="msgs" aria-live="polite">
        {msgs.map((m) => (
          <div key={m.id} className={`msg ${m.aviso ? 'aviso' : m.role}`}>
            {m.aviso && <span className="meta" style={{ marginTop: 0, marginBottom: 4 }}>💬 Mensaje automático</span>}
            {m.text}
            {m.share && <a className="btn sm" style={{ marginTop: 10, display: 'flex' }} href={m.share.url} target="_blank" rel="noreferrer">{m.share.label}</a>}
            <span className="meta">{fmtTime(m.at)}</span></div>
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
      {!isSetup && quick.length === 0 && !draft && pending.length === 0 && msgs.length <= 2 && (
        <div className="starter">
          <span className="faint">Habla con el micrófono entre cliente y cliente. Se guarda al toque; si te equivocas, di «deshacer». Ejemplos:</span>
          {(ctx.business.kind === 'verduras'
            ? [['Vendí 3 soles de tomate y un kilo de papa en efectivo', 'Varias ventas en un audio'], ['En esta última hora vendí como 60 en efectivo', 'Si no pudiste anotar cada venta'],
              ['Se me malogró medio saco de tomate', 'Una pérdida'], ['Cerrar mi día', 'Contar tu plata en la noche']]
            : [['Vendí 3 polos por 50 soles en efectivo', 'Registrar una venta'], ['Gasté 15 en pasajes', 'Registrar un gasto'],
              ['Se me rompió la balanza, valía 120', 'Una pérdida'], ['Cerrar mi día', 'Contar tu plata en la noche']]).map(([t, h]) => (
            <button key={t} onClick={() => sendText(t)}>«{t}»<small>{h}</small></button>
          ))}
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
