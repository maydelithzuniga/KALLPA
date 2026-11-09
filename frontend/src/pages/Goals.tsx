import { useEffect, useState } from 'react'
import type { Ctx } from '../App'
import { get, send, soles, toCents, uid } from '../lib/api'
import type { Goal } from '../lib/types'
import { Progress } from '../components/charts'
import { Sheet } from '../components/ui'
import { IconPlus } from '../components/icons'

export default function Goals({ ctx }: { ctx: Ctx }) {
  const bid = ctx.business.id
  const [goals, setGoals] = useState<Goal[] | null>(null)
  const [creating, setCreating] = useState(false)
  const [saving, setSaving] = useState<Goal | null>(null)

  useEffect(() => { get<Goal[]>(`/api/businesses/${bid}/goals`).then(setGoals).catch(() => setGoals([])) }, [bid, ctx.tick])

  async function setStatus(g: Goal, status: string) {
    await send(`/api/goals/${g.id}`, { status }, 'PATCH')
    ctx.refresh()
  }

  const active = goals?.filter((g) => g.status === 'activa') ?? []
  const done = goals?.filter((g) => g.status !== 'activa') ?? []
  return (
    <div className="wrap">
      <div className="hello spread" style={{ alignItems: 'flex-end' }}>
        <div><h1>Metas</h1><p style={{ textTransform: 'none' }}>Te digo cuánto separar según lo que de verdad ganas.</p></div>
        <button className="btn sm" onClick={() => setCreating(true)}><IconPlus width={18} /> Nueva meta</button>
      </div>
      {goals === null && <div className="empty">Cargando…</div>}
      {goals?.length === 0 && (
        <div className="qcard" style={{ textAlign: 'center' }}>
          <p style={{ marginTop: 0 }}>Aún no tienes metas.</p>
          <button className="btn" onClick={() => setCreating(true)}>Crear mi primera meta</button>
          <p className="faint">O dime en Dictar: «quiero juntar 1500 para una congeladora en diciembre».</p>
        </div>
      )}
      {active.map((g) => (
        <div className="goal-card" key={g.id}>
          <div className="top">
            <div>
              <span className={`pill ${g.kind === 'reposicion' ? 'accent' : g.behind ? 'warn' : 'good'}`}>
                {g.kind === 'reposicion' ? 'Reponer mercadería' : g.behind ? 'Vas atrasada' : 'Vas bien'}</span>
              <h2 style={{ margin: '8px 0 0' }}>{g.name}</h2>
            </div>
            <div style={{ textAlign: 'right' }}><div className="pct">{g.progress_pct ?? '—'}%</div><small className="faint">de {soles(g.target_cents)}</small></div>
          </div>
          <Progress pct={g.progress_pct} accent={g.behind || g.kind === 'reposicion'} />
          <p className="say" style={{ margin: '12px 0' }}>{g.message}</p>
          {g.kind === 'ahorro' && g.per_week_cents !== undefined && (
            <div className="chips" style={{ marginTop: 0, marginBottom: 12 }}>
              <span className="chip2">Llevas <b>{soles(g.saved_cents ?? 0)}</b></span>
              <span className="chip2">Separa por semana <b>{soles(g.per_week_cents)}</b></span>
              {g.days_left !== undefined && <span className="chip2">Quedan <b>{g.days_left} días</b></span>}
            </div>
          )}
          <div className="row wrap">
            {g.kind === 'ahorro' && <button className="btn sm" onClick={() => setSaving(g)}>Separar plata</button>}
            <button className="btn sm ghost" onClick={() => setStatus(g, 'cumplida')}>¡La cumplí!</button>
            <button className="btn sm ghost" onClick={() => setStatus(g, 'cancelada')}>Quitar</button>
          </div>
        </div>
      ))}
      {done.length > 0 && <><h3 style={{ margin: '16px 0 8px' }}>Cumplidas</h3>{done.map((g) => <div className="card flat" key={g.id}><b>{g.name}</b> · {soles(g.target_cents)} <span className="pill good">cumplida</span></div>)}</>}
      <NewGoal open={creating} bid={bid} onClose={() => setCreating(false)} onSaved={() => { setCreating(false); ctx.refresh() }} />
      <SaveSheet goal={saving} bid={bid} onClose={() => setSaving(null)} onSaved={() => { setSaving(null); ctx.toast('Separado para tu meta.'); ctx.refresh() }} />
    </div>
  )
}

function NewGoal({ open, bid, onClose, onSaved }: { open: boolean; bid: number; onClose: () => void; onSaved: () => void }) {
  const [kind, setKind] = useState<'reposicion' | 'ahorro'>('reposicion')
  const [name, setName] = useState('')
  const [amount, setAmount] = useState('')
  const [deadline, setDeadline] = useState('')
  async function save() {
    await send(`/api/businesses/${bid}/goals`, { kind, name: name || (kind === 'reposicion' ? 'Reponer mercadería' : 'Mi meta'), target_cents: toCents(amount), deadline: deadline || null })
    setName(''); setAmount(''); setDeadline('')
    onSaved()
  }
  return (
    <Sheet open={open} onClose={onClose} title="Nueva meta">
      <div className="seg" style={{ marginBottom: 12 }}>
        <button className={kind === 'reposicion' ? 'on' : ''} onClick={() => setKind('reposicion')}>Reponer inventario</button>
        <button className={kind === 'ahorro' ? 'on' : ''} onClick={() => setKind('ahorro')}>Ahorrar para algo</button>
      </div>
      <label className="field"><span>{kind === 'reposicion' ? '¿Qué vas a comprar?' : '¿Para qué ahorras?'}</span>
        <input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder={kind === 'reposicion' ? 'Ej. 2 docenas de polos' : 'Ej. Congeladora, otro puesto, campaña navideña'} /></label>
      <label className="field"><span>{kind === 'reposicion' ? '¿Cuánto cuesta tu próxima compra? (S/)' : '¿Cuánto necesitas? (S/)'}</span>
        <input className="input" inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} /></label>
      {kind === 'ahorro' && <label className="field"><span>¿Para cuándo?</span><input className="input" type="date" value={deadline} onChange={(e) => setDeadline(e.target.value)} /></label>}
      <button className="btn block" disabled={!amount} onClick={save}>Guardar meta</button>
    </Sheet>
  )
}

function SaveSheet({ goal, bid, onClose, onSaved }: { goal: Goal | null; bid: number; onClose: () => void; onSaved: () => void }) {
  const [amount, setAmount] = useState('')
  const [method, setMethod] = useState<'efectivo' | 'yape'>('efectivo')
  const [op] = useState(uid())
  if (!goal) return null
  async function save() {
    await send(`/api/businesses/${bid}/movements`, { kind: 'ahorro_meta', goal_id: goal!.id, amount_cents: toCents(amount), method, op_id: op + amount + method })
    setAmount('')
    onSaved()
  }
  return (
    <Sheet open onClose={onClose} title={`Separar para «${goal.name}»`}>
      {goal.per_week_cents !== undefined && <p className="muted">Te sugiero separar {soles(goal.per_week_cents)} esta semana.</p>}
      <label className="field"><span>Monto (S/)</span><input className="input" inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} /></label>
      <div className="seg" style={{ marginBottom: 12 }}>
        <button className={method === 'efectivo' ? 'on' : ''} onClick={() => setMethod('efectivo')}>Del efectivo</button>
        <button className={method === 'yape' ? 'on' : ''} onClick={() => setMethod('yape')}>Del Yape</button>
      </div>
      <button className="btn block" disabled={!amount} onClick={save}>Separar</button>
    </Sheet>
  )
}
