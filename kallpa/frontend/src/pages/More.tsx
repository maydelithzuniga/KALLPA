import { useEffect, useState } from 'react'
import type { Ctx } from '../App'
import { apiBase, fmtDate, get, send, setApiBase, soles, toCents, upload } from '../lib/api'
import type { Movement } from '../lib/types'
import { checkPill, KV, methodPill, originPill, Sheet } from '../components/ui'
import { IconBack, IconDoc, IconGear, IconList } from '../components/icons'
import Report from './Report'

export default function More({ ctx }: { ctx: Ctx }) {
  const [view, setView] = useState<string | null>(ctx.sub)
  useEffect(() => setView(ctx.sub), [ctx.sub])
  if (view === 'historial') return <Sub title="Historial" back={() => setView(null)}><History ctx={ctx} /></Sub>
  if (view === 'reporte') return <Sub title="Reporte para el banco" back={() => setView(null)}><Report ctx={ctx} /></Sub>
  if (view === 'ajustes') return <Sub title="Ajustes" back={() => setView(null)}><Settings ctx={ctx} /></Sub>
  return (
    <div>
      <h1 style={{ marginBottom: 12 }}>Más</h1>
      <button className="choice" onClick={() => setView('reporte')}><IconDoc width={26} /><span><b>Reporte para el banco</b><span className="faint">Tus ingresos y capacidad de pago para pedir un préstamo</span></span></button>
      <button className="choice" onClick={() => setView('historial')}><IconList width={26} /><span><b>Historial</b><span className="faint">Todos tus movimientos, correcciones y respaldos</span></span></button>
      <button className="choice" onClick={() => setView('ajustes')}><IconGear width={26} /><span><b>Ajustes</b><span className="faint">Saldo inicial, gastos fijos, deudas, equipos y conexión</span></span></button>
    </div>
  )
}

function Sub({ title, back, children }: { title: string; back: () => void; children: React.ReactNode }) {
  return (
    <div>
      <div className="row no-print" style={{ marginBottom: 12 }}>
        <button className="iconbtn" onClick={back} aria-label="Volver"><IconBack /></button>
        <h1>{title}</h1>
      </div>
      {children}
    </div>
  )
}

const KIND_ICON: Record<string, [string, string]> = {
  venta: ['🛍️', 'var(--good-soft)'], compra: ['📦', 'var(--brand-soft)'], gasto: ['🧾', 'var(--warn-soft)'],
  retiro_personal: ['🏠', 'var(--accent-soft)'], aporte: ['💵', 'var(--brand-soft)'], traslado: ['🔁', 'var(--surface-2)'],
  cobro_fiado: ['🤝', 'var(--good-soft)'], pago_deuda: ['🏦', 'var(--warn-soft)'], saldo_inicial: ['🏁', 'var(--surface-2)'],
  ajuste_stock: ['⚖️', 'var(--surface-2)'], ahorro_meta: ['🎯', 'var(--yape-soft)'],
}
const IN_KINDS = new Set(['venta', 'cobro_fiado', 'aporte', 'saldo_inicial'])

function History({ ctx }: { ctx: Ctx }) {
  const bid = ctx.business.id
  const [rows, setRows] = useState<Movement[] | null>(null)
  const [filter, setFilter] = useState('')
  const [sel, setSel] = useState<number | null>(null)
  useEffect(() => {
    get<Movement[]>(`/api/businesses/${bid}/movements?limit=200${filter ? `&kind=${filter}` : ''}`).then(setRows).catch(() => setRows([]))
  }, [bid, filter, ctx.tick])
  return (
    <div>
      <select className="input" value={filter} onChange={(e) => setFilter(e.target.value)} style={{ marginBottom: 10 }}>
        <option value="">Todos los movimientos</option>
        <option value="venta">Ventas</option><option value="compra">Compras</option><option value="gasto">Gastos del negocio</option>
        <option value="retiro_personal">Retiros para la casa</option><option value="aporte">Aportes propios</option>
        <option value="traslado">Traslados</option><option value="cobro_fiado">Cobros de fiado</option><option value="pago_deuda">Cuotas</option>
      </select>
      {rows === null && <div className="empty">Cargando…</div>}
      <div className="card">
        <ul className="list">
          {rows?.map((m) => {
            const [ic, bg] = KIND_ICON[m.kind] ?? ['•', 'var(--surface-2)']
            const sign = IN_KINDS.has(m.kind) ? '+' : m.kind === 'traslado' || m.kind === 'ajuste_stock' ? '' : '−'
            return (
              <li key={m.id}>
                <button className={`mv ${m.status === 'anulado' ? 'void' : ''}`} onClick={() => setSel(m.id)}>
                  <span className="ic" style={{ background: bg }}>{ic}</span>
                  <span className="body">
                    <b>{m.product ? `${m.quantity ?? ''} ${m.product}` : m.category || m.label}{m.counterparty ? ` · ${m.counterparty}` : ''}</b>
                    <span className="faint">{fmtDate(m.occurred_at, true)} · {m.label}{m.revision > 1 ? ' · corregido' : ''}{m.status === 'anulado' ? ' · anulado' : ''}</span>
                  </span>
                  <span>
                    <div className={`amt ${IN_KINDS.has(m.kind) ? 'in' : 'out'}`}>{sign}{soles(m.kind === 'venta' ? m.amount_cents : m.amount_cents)}</div>
                    <div className="row" style={{ justifyContent: 'flex-end', gap: 4 }}>{methodPill(m.method)}</div>
                  </span>
                </button>
              </li>
            )
          })}
        </ul>
        {rows?.length === 0 && <div className="empty">Aún no hay movimientos.</div>}
      </div>
      <MovementSheet id={sel} onClose={() => setSel(null)} ctx={ctx} />
    </div>
  )
}

function MovementSheet({ id, onClose, ctx }: { id: number | null; onClose: () => void; ctx: Ctx }) {
  const [m, setM] = useState<Movement | null>(null)
  const [edit, setEdit] = useState(false)
  const [amount, setAmount] = useState('')
  const [qty, setQty] = useState('')
  const [method, setMethod] = useState('')
  useEffect(() => {
    if (id === null) { setM(null); return }
    get<Movement>(`/api/movements/${id}`).then((x) => { setM(x); setAmount(String(x.amount_cents / 100)); setQty(x.quantity ? String(x.quantity) : ''); setMethod(x.method ?? ''); setEdit(false) })
  }, [id])
  if (id === null || !m) return null
  async function saveEdit() {
    const changes: Record<string, unknown> = { amount_cents: toCents(amount) }
    if (qty) changes.quantity = parseInt(qty)
    if (method) changes.method = method
    try {
      setM(await send<Movement>(`/api/movements/${m!.id}`, { changes, reason: 'corrección desde la app' }, 'PATCH'))
      setEdit(false); ctx.toast('Corregido. El cambio quedó en el historial.'); ctx.refresh()
    } catch (e) { ctx.toast((e as Error).message) }
  }
  async function voidIt() {
    if (!confirm('¿Anular este movimiento? Se revierten sus efectos en caja y stock.')) return
    setM(await send<Movement>(`/api/movements/${m!.id}/void`))
    ctx.refresh()
  }
  async function attach(file: File, kind: string) {
    const f = new FormData()
    f.append('file', file); f.append('kind', kind)
    setM(await upload<Movement>(`/api/movements/${m!.id}/attachments`, f))
    ctx.toast('Adjunto guardado.'); ctx.refresh()
  }
  return (
    <Sheet open onClose={onClose} title={`${m.label[0].toUpperCase()}${m.label.slice(1)}`}>
      <div className="row wrap" style={{ marginBottom: 8 }}>
        {originPill(m.origin, m.origin_label)}{checkPill(m.check, m.check_label)}{m.demo && <span className="pill warn">Demo</span>}
        {m.status === 'anulado' && <span className="pill bad">Anulado</span>}
      </div>
      <div className="card flat">
        <KV k="Fecha" v={fmtDate(m.occurred_at, true)} />
        {m.product && <KV k="Producto" v={`${m.quantity ?? '?'} × ${m.product}`} />}
        {m.kind === 'venta' && m.reference_total_cents !== null && <KV k="Precio habitual" v={`${soles(m.unit_price_ref_cents)} c/u · ${soles(m.reference_total_cents)}`} />}
        <KV k={m.kind === 'venta' ? 'Precio final cobrado' : 'Monto'} v={soles(m.amount_cents)} />
        {m.kind === 'venta' && <KV k="Descuento" v={m.discount_cents === null ? 'Sin calcular (no hay precio habitual)' : soles(m.discount_cents)} />}
        {m.kind === 'venta' && m.paid_cents !== m.amount_cents && <KV k="Cobrado / pendiente" v={`${soles(m.paid_cents)} / ${soles(m.pending_cents)}`} />}
        {m.kind === 'venta' && <KV k="Margen" v={m.margin_cents === null ? 'Pendiente: falta el costo' : soles(m.margin_cents)} />}
        {m.kind === 'compra' && <KV k="Costo unitario" v={m.unit_cost_cents ? soles(m.unit_cost_cents) : 'Unidades pendientes'} />}
        {m.method && <KV k="Medio" v={m.to_method ? `${m.method} → ${m.to_method}` : m.method} />}
        {m.counterparty && <KV k="Persona" v={m.counterparty} />}
        {m.category && <KV k="Categoría" v={m.category} />}
        {m.raw_text && <KV k="Lo que dictaste" v={`«${m.raw_text}»`} />}
        {m.yape?.map((y) => <KV key={y.operation_code} k="Cobro Yape vinculado" v={`${y.payer} · ${soles(y.amount_cents)} · ${y.operation_code}${y.demo ? ' (demo)' : ''}`} />)}
        {m.attachments.map((a) => <KV key={a.id} k="Adjunto" v={<a href={`${apiBase()}/api/attachments/${a.filename}`} target="_blank" rel="noreferrer">{a.kind.replace('_', ' ')}</a>} />)}
      </div>
      {m.revisions && m.revisions.length > 0 && (
        <div className="card flat">
          <h3>Cambios</h3>
          {m.revisions.map((r, i) => (
            <div key={i} className="small" style={{ padding: '6px 0', borderBottom: '1px solid var(--line)' }}>
              {fmtDate(r.changed_at, true)} · {r.reason}<br />
              <span className="faint">Antes: {soles(r.before.amount_cents as number)}{r.before.quantity ? ` · ${r.before.quantity} u.` : ''} {String(r.before.method ?? '')} → Ahora: {soles(r.after.amount_cents as number)}{r.after.quantity ? ` · ${r.after.quantity} u.` : ''} {String(r.after.method ?? '')}</span>
            </div>
          ))}
        </div>
      )}
      {m.status === 'confirmado' && !edit && (
        <div className="stack">
          <div className="row">
            <button className="btn ghost" style={{ flex: 1 }} onClick={() => setEdit(true)}>Corregir</button>
            <button className="btn danger" style={{ flex: 1 }} onClick={voidIt}>Anular</button>
          </div>
          <label className="btn line block" style={{ cursor: 'pointer' }}>
            Adjuntar {m.kind === 'compra' ? 'comprobante del proveedor' : m.method === 'yape' ? 'captura de Yape' : 'respaldo'}
            <input type="file" accept="image/*,application/pdf" hidden onChange={(e) => e.target.files?.[0] && attach(e.target.files[0], m.kind === 'compra' ? 'comprobante_proveedor' : m.method === 'yape' ? 'captura_yape' : 'otro')} />
          </label>
        </div>
      )}
      {edit && (
        <div className="card flat">
          <label className="field"><span>{m.kind === 'venta' ? 'Precio final total (S/)' : 'Monto (S/)'}</span><input className="input" inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} /></label>
          {m.product && <label className="field"><span>Cantidad</span><input className="input" inputMode="numeric" value={qty} onChange={(e) => setQty(e.target.value)} /></label>}
          {m.method && m.kind !== 'traslado' && (
            <div className="seg" style={{ marginBottom: 10 }}>
              <button className={method === 'efectivo' ? 'on' : ''} onClick={() => setMethod('efectivo')}>Efectivo</button>
              <button className={method === 'yape' ? 'on' : ''} onClick={() => setMethod('yape')}>Yape</button>
            </div>
          )}
          <button className="btn block" onClick={saveEdit}>Guardar corrección</button>
        </div>
      )}
    </Sheet>
  )
}

function Settings({ ctx }: { ctx: Ctx }) {
  const bid = ctx.business.id
  const [ef, setEf] = useState('')
  const [ya, setYa] = useState('')
  const [fixed, setFixed] = useState<{ id: number; name: string; amount_cents: number; due_day: number }[]>([])
  const [debts, setDebts] = useState<{ id: number; creditor: string; installment_cents: number; due_day: number; remaining_cents: number }[]>([])
  const [assets, setAssets] = useState<{ id: number; name: string; value_cents: number }[]>([])
  const [fx, setFx] = useState({ name: '', amount: '', day: '1' })
  const [db, setDb] = useState({ creditor: '', total: '', inst: '', day: '15' })
  const [as, setAs] = useState({ name: '', value: '' })
  const [api, setApi] = useState(apiBase())
  const [name, setName] = useState(ctx.business.name)
  const [owner, setOwner] = useState(ctx.business.owner_name ?? '')

  const load = () => {
    get<typeof fixed>(`/api/businesses/${bid}/fixed-expenses`).then(setFixed).catch(() => undefined)
    get<typeof debts>(`/api/businesses/${bid}/debts`).then(setDebts).catch(() => undefined)
    get<typeof assets>(`/api/businesses/${bid}/assets`).then(setAssets).catch(() => undefined)
  }
  useEffect(load, [bid])

  async function opening() {
    const body: Record<string, number | null> = {}
    if (ef) body.efectivo_cents = toCents(ef)
    if (ya) body.yape_cents = toCents(ya)
    await send(`/api/businesses/${bid}/opening`, body)
    setEf(''); setYa(''); ctx.toast('Saldo inicial guardado.'); ctx.refresh()
  }
  const h = ctx.health
  return (
    <div>
      <div className="card">
        <h2>Tu negocio</h2>
        <label className="field"><span>Nombre</span><input className="input" value={name} onChange={(e) => setName(e.target.value)} /></label>
        <label className="field"><span>Tu nombre</span><input className="input" value={owner} onChange={(e) => setOwner(e.target.value)} /></label>
        <button className="btn sm" onClick={async () => { await send(`/api/businesses/${bid}`, { name, owner_name: owner || null }, 'PATCH'); ctx.toast('Guardado.'); ctx.refresh() }}>Guardar</button>
      </div>
      <div className="card">
        <h2>Saldo inicial</h2>
        <p className="faint" style={{ marginTop: 0 }}>Lo que tenías cuando empezaste a registrar. Sin esto solo puedo mostrar el flujo.</p>
        <div className="grid2">
          <label className="field"><span>Efectivo (S/)</span><input className="input" inputMode="decimal" value={ef} onChange={(e) => setEf(e.target.value)} /></label>
          <label className="field"><span>Yape (S/)</span><input className="input" inputMode="decimal" value={ya} onChange={(e) => setYa(e.target.value)} /></label>
        </div>
        <button className="btn sm" disabled={!ef && !ya} onClick={opening}>Guardar saldo inicial</button>
      </div>
      <div className="card">
        <h2>Gastos fijos del mes</h2>
        <p className="faint" style={{ marginTop: 0 }}>Para calcular tu punto de equilibrio y avisarte de pagos próximos.</p>
        {fixed.map((f) => <div className="kv" key={f.id}><span>{f.name} · día {f.due_day}</span><span>{soles(f.amount_cents)} <button className="btn sm ghost" onClick={async () => { await send(`/api/fixed-expenses/${f.id}`, undefined, 'DELETE'); load(); ctx.refresh() }}>✕</button></span></div>)}
        <div className="grid3" style={{ marginTop: 8 }}>
          <input className="input" placeholder="Alquiler" value={fx.name} onChange={(e) => setFx({ ...fx, name: e.target.value })} />
          <input className="input" placeholder="S/" inputMode="decimal" value={fx.amount} onChange={(e) => setFx({ ...fx, amount: e.target.value })} />
          <input className="input" placeholder="Día" inputMode="numeric" value={fx.day} onChange={(e) => setFx({ ...fx, day: e.target.value })} />
        </div>
        <button className="btn sm" style={{ marginTop: 8 }} disabled={!fx.name || !fx.amount} onClick={async () => { await send(`/api/businesses/${bid}/fixed-expenses`, { name: fx.name, amount_cents: toCents(fx.amount), due_day: parseInt(fx.day) || 1 }); setFx({ name: '', amount: '', day: '1' }); load(); ctx.refresh() }}>Agregar</button>
      </div>
      <div className="card">
        <h2>Deudas y cuotas</h2>
        {debts.map((d) => <div className="kv" key={d.id}><span>{d.creditor} · día {d.due_day}</span><span>{soles(d.installment_cents)}/mes · faltan {soles(d.remaining_cents)}</span></div>)}
        <div className="grid2" style={{ marginTop: 8 }}>
          <input className="input" placeholder="¿A quién?" value={db.creditor} onChange={(e) => setDb({ ...db, creditor: e.target.value })} />
          <input className="input" placeholder="Total S/" inputMode="decimal" value={db.total} onChange={(e) => setDb({ ...db, total: e.target.value })} />
          <input className="input" placeholder="Cuota S/" inputMode="decimal" value={db.inst} onChange={(e) => setDb({ ...db, inst: e.target.value })} />
          <input className="input" placeholder="Día de pago" inputMode="numeric" value={db.day} onChange={(e) => setDb({ ...db, day: e.target.value })} />
        </div>
        <button className="btn sm" style={{ marginTop: 8 }} disabled={!db.creditor || !db.total || !db.inst} onClick={async () => { await send(`/api/businesses/${bid}/debts`, { creditor: db.creditor, total_cents: toCents(db.total), installment_cents: toCents(db.inst), due_day: parseInt(db.day) || 15 }); setDb({ creditor: '', total: '', inst: '', day: '15' }); load(); ctx.refresh() }}>Agregar</button>
      </div>
      <div className="card">
        <h2>Equipos del negocio</h2>
        <p className="faint" style={{ marginTop: 0 }}>Se muestran en tu reporte como capital declarado.</p>
        {assets.map((a) => <div className="kv" key={a.id}><span>{a.name}</span><span>{soles(a.value_cents)}</span></div>)}
        <div className="grid2" style={{ marginTop: 8 }}>
          <input className="input" placeholder="Ej. Congeladora" value={as.name} onChange={(e) => setAs({ ...as, name: e.target.value })} />
          <input className="input" placeholder="Valor S/" inputMode="decimal" value={as.value} onChange={(e) => setAs({ ...as, value: e.target.value })} />
        </div>
        <button className="btn sm" style={{ marginTop: 8 }} disabled={!as.name || !as.value} onClick={async () => { await send(`/api/businesses/${bid}/assets`, { name: as.name, value_cents: toCents(as.value) }); setAs({ name: '', value: '' }); load() }}>Agregar</button>
      </div>
      <div className="card">
        <h2>Conexión</h2>
        <KV k="Voz en el servidor" v={h?.transcription.model_on_disk ? 'Lista (faster-whisper)' : h?.transcription.installed ? 'Falta descargar el modelo' : 'No instalada (uso la del celular)'} />
        <KV k="IA para configurar" v={h?.gemini.enabled ? `Activa · ${h.gemini.model}` : 'Desactivada (plantillas locales)'} />
        <KV k="WhatsApp" v={h?.whatsapp.status ?? '—'} />
        <label className="field" style={{ marginTop: 10 }}><span>Servidor (para la app Android)</span>
          <input className="input" value={api} onChange={(e) => setApi(e.target.value)} placeholder="https://tu-servidor" /></label>
        <button className="btn sm ghost" onClick={() => { setApiBase(api); location.reload() }}>Guardar servidor</button>
      </div>
      <div className="card">
        <h2>Demo</h2>
        <div className="row wrap">
          <button className="btn sm ghost" onClick={ctx.switchBusiness}>Cambiar de negocio</button>
          {ctx.business.demo && <button className="btn sm ghost" onClick={async () => { await send('/api/demo/reset'); ctx.toast('Datos de demostración reiniciados.'); ctx.switchBusiness() }}>Reiniciar datos demo</button>}
        </div>
      </div>
    </div>
  )
}
