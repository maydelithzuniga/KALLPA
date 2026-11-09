import { useEffect, useRef, useState } from 'react'
import { get, send, upload } from '../lib/api'
import type { Business, Health, Proposal } from '../lib/types'
import { browserRecognizer, extFor, Recorder } from '../lib/voice'
import { IconMic, IconStop } from '../components/icons'

type Props = { business: Business | null; health: Health | null; online: boolean; onReady: (b: Business) => void; onPick: (id: number) => void }

const KIND_LABEL: Record<string, string> = { reventa: 'Reventa', comida: 'Comida preparada', servicios: 'Servicios' }

export default function Onboarding({ business, health, online, onReady, onPick }: Props) {
  const [list, setList] = useState<Business[] | null>(null)
  const [step, setStep] = useState<'pick' | 'name' | 'tell' | 'review'>(business ? 'tell' : 'pick')
  const [biz, setBiz] = useState<Business | null>(business)
  const [name, setName] = useState('')
  const [owner, setOwner] = useState('')
  const [desc, setDesc] = useState('')
  const [proposal, setProposal] = useState<Proposal | null>(business?.setup_proposal ?? null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [recording, setRecording] = useState(false)
  const rec = useRef<Recorder | null>(null)

  useEffect(() => { get<Business[]>('/api/businesses').then(setList).catch(() => setList([])) }, [])
  useEffect(() => { if (business?.setup_proposal) { setProposal(business.setup_proposal); setStep('review') } }, [business])

  const serverVoice = !!health?.transcription.installed && !!health?.transcription.model_on_disk

  async function create() {
    setBusy(true); setErr(null)
    try {
      const b = await send<Business>('/api/businesses', { name: name || 'Mi negocio', owner_name: owner || null })
      setBiz(b); setStep('tell')
    } catch { setErr('No pude conectar con el servidor. Revisa tu conexión.') }
    setBusy(false)
  }

  async function propose(text: string) {
    if (!biz) return
    setBusy(true); setErr(null)
    try {
      const r = await send<{ proposal: Proposal }>(`/api/businesses/${biz.id}/setup/propose`, { description: text, use_ai: true })
      setProposal(r.proposal); setStep('review')
    } catch { setErr('No pude preparar la propuesta. Intenta otra vez o elige una plantilla.') }
    setBusy(false)
  }

  async function toggleMic() {
    if (recording) {
      setRecording(false)
      if (rec.current) {
        const blob = await rec.current.stop()
        if (!biz) return
        setBusy(true)
        const f = new FormData()
        f.append('audio', blob, 'descripcion' + extFor(blob.type))
        f.append('use_ai', 'true')
        try {
          const r = await upload<{ transcript: string; proposal: Proposal }>(`/api/businesses/${biz.id}/setup/transcribe-propose`, f)
          setDesc(r.transcript); setProposal(r.proposal); setStep('review')
        } catch { setErr('No pude transcribir el audio. Escríbelo o elige una plantilla.') }
        setBusy(false)
      }
      return
    }
    setErr(null)
    if (serverVoice && Recorder.supported()) {
      try { rec.current = new Recorder(); await rec.current.start(); setRecording(true) } catch { setErr('No tengo permiso para usar el micrófono.') }
      return
    }
    const sr = browserRecognizer()
    if (!sr) { setErr('Tu navegador no permite dictar aquí. Escríbelo.'); return }
    setRecording(true)
    sr.onresult = (e) => { const t = e.results[0][0].transcript; setDesc(t); propose(t) }
    sr.onerror = () => setErr('No te escuché bien. Intenta otra vez.')
    sr.onend = () => setRecording(false)
    sr.start()
  }

  async function template(kind: string) {
    if (!biz) return
    setBusy(true)
    try { onReady(await send<Business>(`/api/businesses/${biz.id}/setup/template`, { kind })) } catch { setErr('No pude guardar.') }
    setBusy(false)
  }

  async function confirm() {
    if (!biz || !proposal) return
    setBusy(true)
    const clean = { ...proposal, products: proposal.products.filter((p) => p.name.trim()) }
    try { onReady(await send<Business>(`/api/businesses/${biz.id}/setup/confirm`, { proposal: clean })) } catch { setErr('No pude guardar.') }
    setBusy(false)
  }

  const setProd = (i: number, name: string) => proposal && setProposal({ ...proposal, products: proposal.products.map((p, j) => j === i ? { ...p, name } : p) })
  const delProd = (i: number) => proposal && setProposal({ ...proposal, products: proposal.products.filter((_, j) => j !== i) })

  if (step === 'pick') {
    return (
      <div className="narrow">
        <div className="welcome">
          <img src="/icon.svg" alt="" />
          <h1>Kallpa</h1>
          <p className="muted">Tu amiga que sabe de números. Dicta tus ventas y gastos, mira tu caja y arma tu reporte para el banco.</p>
        </div>
        {!online && <div className="banner warn">Sin conexión. Conéctate una vez para empezar.</div>}
        <button className="btn block" onClick={() => setStep('name')}>Empezar mi negocio</button>
        <h3 style={{ margin: '22px 0 8px' }}>O entra a una demo</h3>
        {list === null && <p className="faint">Cargando…</p>}
        {list?.filter((b) => b.setup_state === 'listo').map((b) => (
          <button key={b.id} className="choice" onClick={() => onPick(b.id)}>
            <span style={{ fontSize: 26 }}>{b.kind === 'comida' ? '🍲' : b.kind === 'servicios' ? '✂️' : '👕'}</span>
            <span><b>{b.name}</b><span className="faint">{KIND_LABEL[b.kind]}{b.demo ? ' · datos de demostración' : ''}</span></span>
          </button>
        ))}
      </div>
    )
  }

  if (step === 'name') {
    return (
      <div className="narrow" style={{ paddingTop: 24 }}>
        <h1>¿Cómo se llama tu negocio?</h1>
        <p className="muted">Lo puedes cambiar después.</p>
        <label className="field"><span>Nombre del negocio</span><input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="Ej. Polos Rosita" /></label>
        <label className="field"><span>Tu nombre (opcional)</span><input className="input" value={owner} onChange={(e) => setOwner(e.target.value)} placeholder="Ej. Rosa" /></label>
        {err && <div className="banner bad">{err}</div>}
        <button className="btn block" disabled={busy} onClick={create}>Seguir</button>
        <button className="btn ghost block" style={{ marginTop: 8 }} onClick={() => setStep('pick')}>Volver</button>
      </div>
    )
  }

  if (step === 'tell') {
    return (
      <div className="narrow" style={{ paddingTop: 24 }}>
        <h1>Cuéntame qué vendes y cómo te pagan</h1>
        <p className="muted">Por ejemplo: «Vendo polos, compro por docena y cobro por Yape y en efectivo».</p>
        <div style={{ display: 'grid', placeItems: 'center', margin: '22px 0' }}>
          <button className={`mic ${recording ? 'rec' : ''}`} style={{ width: 92, height: 92 }} onClick={toggleMic} disabled={busy || !online}
            aria-label={recording ? 'Terminar de grabar' : 'Hablar'}>
            {recording ? <IconStop /> : <IconMic />}
          </button>
          <p className="faint">{recording ? 'Te escucho… toca para terminar' : busy ? 'Pensando…' : 'Toca y habla'}</p>
        </div>
        <label className="field"><span>O escríbelo</span>
          <textarea className="input" rows={3} value={desc} onChange={(e) => setDesc(e.target.value)} placeholder="Vendo…" />
        </label>
        {err && <div className="banner bad">{err}</div>}
        <button className="btn block" disabled={busy || desc.trim().length < 3} onClick={() => propose(desc)}>Ver propuesta</button>
        <h3 style={{ margin: '22px 0 8px' }}>¿Prefieres configurarlo tú?</h3>
        <p className="faint">Usa una plantilla local (no necesita internet externo ni IA).</p>
        {['reventa', 'comida', 'servicios'].map((k) => (
          <button key={k} className="choice" disabled={busy} onClick={() => template(k)}>
            <span style={{ fontSize: 24 }}>{k === 'comida' ? '🍲' : k === 'servicios' ? '✂️' : '👕'}</span>
            <span><b>{KIND_LABEL[k]}</b><span className="faint">{health?.templates?.[k]}</span></span>
          </button>
        ))}
      </div>
    )
  }

  return (
    <div className="narrow" style={{ paddingTop: 24 }}>
      <h1>¿Lo guardo así?</h1>
      <p className="muted">Revisa y corrige. Los precios, costos y stock me los dices cuando quieras.</p>
      {proposal?.note && <div className="banner info">{proposal.note}</div>}
      {proposal && (
        <div className="card">
          <div className="spread"><span className="muted">Tipo</span>
            <select className="input" style={{ width: 'auto' }} value={proposal.kind} onChange={(e) => setProposal({ ...proposal, kind: e.target.value as Proposal['kind'] })}>
              {Object.keys(KIND_LABEL).map((k) => <option key={k} value={k}>{KIND_LABEL[k]}</option>)}
            </select>
          </div>
          <h3 style={{ margin: '14px 0 6px' }}>Lo que vendes</h3>
          {proposal.products.map((p, i) => (
            <div className="row" key={i} style={{ marginBottom: 6 }}>
              <input className="input" value={p.name} onChange={(e) => setProd(i, e.target.value)} />
              {p.is_input && <span className="pill">insumo</span>}
              <button className="iconbtn" onClick={() => delProd(i)} aria-label="Quitar">✕</button>
            </div>
          ))}
          <button className="btn ghost sm" onClick={() => setProposal({ ...proposal, products: [...proposal.products, { name: '', aliases: [] }] })}>+ Agregar producto</button>
          <h3 style={{ margin: '14px 0 6px' }}>Cómo te pagan</h3>
          <div className="row wrap">{proposal.payment_methods.map((m) => <span key={m} className={`pill ${m === 'yape' ? 'yape' : 'cash'}`}>{m === 'yape' ? 'Yape' : 'Efectivo'}</span>)}</div>
          <h3 style={{ margin: '14px 0 6px' }}>Categorías</h3>
          <div className="row wrap">{proposal.categories.map((c) => <span key={c.name} className="pill">{c.name}</span>)}</div>
          <p className="faint" style={{ marginTop: 10 }}>Propuesta hecha con {proposal.source === 'gemini' ? 'IA (una sola consulta)' : 'plantilla local'}.</p>
        </div>
      )}
      {err && <div className="banner bad">{err}</div>}
      <button className="btn block" disabled={busy} onClick={confirm}>Sí, guardar</button>
      <button className="btn ghost block" style={{ marginTop: 8 }} onClick={() => setStep('tell')}>Contarlo de nuevo</button>
    </div>
  )
}
