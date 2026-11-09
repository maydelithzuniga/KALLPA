import { useEffect, useState } from 'react'
import type { Ctx } from '../App'
import { apiBase, botNumber, fmtDate, get, send, setApiBase, setBotNumber, soles, toCents, upload, waLinkFor } from '../lib/api'
import type { Movement } from '../lib/types'
import { checkPill, KV, methodPill, originPill, Sheet } from '../components/ui'
import { IconBack, IconBox, IconChevron, IconDoc, IconGear, IconList } from '../components/icons'
import Report from './Report'

export default function More({ ctx }: { ctx: Ctx }) {
  const [view, setView] = useState<string | null>(ctx.sub)
  useEffect(() => setView(ctx.sub), [ctx.sub])
  if (view === 'historial') return <Sub title="Historial" back={() => { setView(null); ctx.go('mas') }}><History ctx={ctx} /></Sub>
  if (view === 'reporte') return <Sub title="Informe para el BCP" back={() => { setView(null); ctx.go('mas') }}><Report ctx={ctx} /></Sub>
  if (view === 'ajustes') return <Sub title="Ajustes" back={() => { setView(null); ctx.go('mas') }}><Settings ctx={ctx} /></Sub>
  const items: { icon: JSX.Element; title: string; sub: string; go: () => void }[] = [
    { icon: <IconBox />, title: 'Mercadería', sub: 'Tu stock, precios y conteos', go: () => ctx.go('stock') },
    { icon: <IconDoc />, title: 'Informe para el BCP', sub: 'Tus ingresos y gastos por Yape verificados', go: () => setView('reporte') },
    { icon: <IconList />, title: 'Historial', sub: 'Todo lo que registraste, para revisar o corregir', go: () => setView('historial') },
    { icon: <IconGear />, title: 'Ajustes', sub: 'Saldo inicial, gastos fijos, deudas y equipos', go: () => setView('ajustes') },
  ]
  return (
    <div className="wrap">
      <div className="hello"><h1>Más</h1></div>
      <div className="listbox">
        {items.map((it) => (
          <button key={it.title} className="lrow" onClick={it.go}>
            <span className="ico">{it.icon}</span>
            <span className="txt"><b>{it.title}</b><small>{it.sub}</small></span>
            <IconChevron className="chev" />
          </button>
        ))}
      </div>
      <p className="faint" style={{ textAlign: 'center' }}>WhatsApp: {ctx.health?.whatsapp.status ?? 'pendiente de conectar'}</p>
    </div>
  )
}

function Sub({ title, back, children }: { title: string; back: () => void; children: React.ReactNode }) {
  return (
    <div className="wrap" style={{ maxWidth: title.startsWith('Informe') ? 980 : undefined }}>
      <div className="row no-print" style={{ margin: '4px 0 22px', gap: 14 }}>
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
                    <div className="row" style={{ justifyContent: 'flex-end', gap: 4 }}>{methodPill(m.method)}{m.yape_direction && m.status === 'confirmado' && <span className={`pill ${m.yape_verified ? 'good' : 'warn'}`}>{m.yape_verified ? '✓' : 'sin verificar'}</span>}</div>
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
  const [askVoid, setAskVoid] = useState(false)
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
    setAskVoid(false)
    setM(await send<Movement>(`/api/movements/${m!.id}/void`))
    ctx.refresh()
  }
  async function verifyYape() {
    await send(`/api/businesses/${ctx.business.id}/yape/demo`, { movement_id: m!.id, payer: m!.counterparty ?? undefined, amount_cents: m!.paid_cents })
    setM(await get<Movement>(`/api/movements/${m!.id}`))
    ctx.toast('Verificado con Yape. Ya entra a tu informe del BCP.'); ctx.refresh()
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
        {originPill(m.origin, m.origin_label)}{m.check && m.check !== 'sin_datos' && checkPill(m.check, m.check_label)}{m.demo && <span className="pill warn">Demo</span>}
        {m.status === 'anulado' && <span className="pill bad">Anulado</span>}
      </div>
      {m.status === 'confirmado' && (m.yape_direction ? (
        m.yape_verified
          ? <div className="banner info">✅ Verificado con Yape: entra a tu informe del BCP.</div>
          : <div className="banner warn"><span className="grow">Por Yape, aún sin verificar: todavía no entra a tu informe del BCP.</span>
              <button className="btn sm" onClick={verifyYape}>Verificar con Yape (simulado)</button></div>
      ) : m.method === 'efectivo' && ['venta', 'cobro_fiado', 'compra', 'gasto', 'pago_deuda', 'retiro_personal'].includes(m.kind)
        ? <div className="banner" style={{ background: 'var(--surface-2)', color: 'var(--ink-2)' }}>En efectivo: no entra al informe del BCP.</div> : null)}
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
            <button className="btn danger" style={{ flex: 1 }} onClick={() => setAskVoid(true)}>Anular</button>
          </div>
          {askVoid && (
            <div className="banner bad">
              <span className="grow">¿Anular este movimiento? Se revierten sus efectos en caja y stock y queda en el historial.</span>
              <div className="row"><button className="btn sm danger" onClick={voidIt}>Sí, anular</button><button className="btn sm ghost" onClick={() => setAskVoid(false)}>No</button></div>
            </div>
          )}
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
  const [fixed, setFixed] = useState<{ id: number; name: string; amount_cents: number; due_day: number; frequency: string; frequency_label: string; cost_type: string; monthly_cents: number }[]>([])
  const [debts, setDebts] = useState<{ id: number; creditor: string; installment_cents: number; due_day: number; remaining_cents: number }[]>([])
  const [assets, setAssets] = useState<{ id: number; name: string; value_cents: number }[]>([])
  const [fx, setFx] = useState({ name: '', amount: '', day: '1', freq: 'mensual', type: '' })
  const [db, setDb] = useState({ creditor: '', total: '', inst: '', day: '15' })
  const [as, setAs] = useState({ name: '', value: '' })
  const [api, setApi] = useState(apiBase())
  const [bot, setBot] = useState(botNumber(ctx.health?.whatsapp.number))
  const [phone, setPhone] = useState(ctx.business.phone ?? '')
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
        <h2>Cuenta tu plata</h2>
        <p className="faint" style={{ marginTop: 0 }}>Cuenta la plata que tienes ahora en tu monedero y mira tu Yape. Desde ahí llevo tu caja.</p>
        <button className="btn sm" style={{ marginBottom: 12 }} onClick={() => ctx.go('chat', 'contar')}>Contarla conversando</button>
        <div className="grid2">
          <label className="field"><span>Efectivo (S/)</span><input className="input" inputMode="decimal" value={ef} onChange={(e) => setEf(e.target.value)} /></label>
          <label className="field"><span>Yape (S/)</span><input className="input" inputMode="decimal" value={ya} onChange={(e) => setYa(e.target.value)} /></label>
        </div>
        <button className="btn sm ghost" disabled={!ef && !ya} onClick={opening}>Guardar lo que tengo hoy</button>
      </div>
      <div className="card">
        <h2>Lo que pagas en tu negocio</h2>
        <p className="faint" style={{ marginTop: 0 }}>
          <b>Fijo</b>: lo pagas vendas o no (alquiler, luz, pasaje al puesto). <b>Variable</b>: sube cuando vendes más (bolsas, flete).
          Todo se lleva a «al mes» para tu punto de equilibrio y tus avisos de pago.
        </p>
        {fixed.map((f) => (
          <div className="kv" key={f.id}>
            <span>{f.name} · <span className={f.cost_type === 'fijo' ? 'pill' : 'pill warn'}>{f.cost_type}</span>
              <small className="faint" style={{ display: 'block' }}>{soles(f.amount_cents)} {f.frequency_label}{f.frequency === 'mensual' ? ` · día ${f.due_day}` : ''}</small></span>
            <span>{soles(f.monthly_cents)}/mes <button className="btn sm ghost" onClick={async () => { await send(`/api/fixed-expenses/${f.id}`, undefined, 'DELETE'); load(); ctx.refresh() }}>✕</button></span>
          </div>
        ))}
        {fixed.length > 0 && (
          <div className="kv" style={{ fontWeight: 600 }}>
            <span>Total al mes</span>
            <span>{soles(fixed.reduce((a, f) => a + f.monthly_cents, 0))} <small className="faint">(fijos {soles(fixed.filter((f) => f.cost_type === 'fijo').reduce((a, f) => a + f.monthly_cents, 0))})</small></span>
          </div>
        )}
        <div className="grid3" style={{ marginTop: 8 }}>
          <input className="input" placeholder="Alquiler" value={fx.name} onChange={(e) => setFx({ ...fx, name: e.target.value })} />
          <input className="input" placeholder="S/" inputMode="decimal" value={fx.amount} onChange={(e) => setFx({ ...fx, amount: e.target.value })} />
          <select className="input" value={fx.freq} onChange={(e) => setFx({ ...fx, freq: e.target.value })}>
            <option value="diario">al día</option><option value="semanal">a la semana</option><option value="quincenal">cada quincena</option>
            <option value="mensual">al mes</option><option value="anual">al año</option>
          </select>
        </div>
        <div className="grid3" style={{ marginTop: 8 }}>
          <select className="input" value={fx.type} onChange={(e) => setFx({ ...fx, type: e.target.value })}>
            <option value="">¿Fijo o variable?</option><option value="fijo">Fijo</option><option value="variable">Variable</option>
          </select>
          {fx.freq === 'mensual' ? <input className="input" placeholder="Día de pago" inputMode="numeric" value={fx.day} onChange={(e) => setFx({ ...fx, day: e.target.value })} /> : <span />}
          <button className="btn sm" disabled={!fx.name || !fx.amount} onClick={async () => {
            await send(`/api/businesses/${bid}/fixed-expenses`, { name: fx.name, amount_cents: toCents(fx.amount), due_day: parseInt(fx.day) || 1, frequency: fx.freq, cost_type: fx.type || null })
            setFx({ name: '', amount: '', day: '1', freq: 'mensual', type: '' }); load(); ctx.refresh()
          }}>Agregar</button>
        </div>
        <p className="faint" style={{ marginBottom: 0 }}>También puedes decirlo por WhatsApp: «pago 15 de bolsas a la semana».</p>
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
        <h2>WhatsApp</h2>
        <p className="faint" style={{ marginTop: 0 }}>Para que tu WhatsApp y la app sean un mismo chat: pon el número de Kallpa (el que configuraron en Meta)
          y tu número. Los botones de WhatsApp abrirán tu WhatsApp, y lo que mandes ahí llega a esta app.</p>
        <label className="field"><span>Número de WhatsApp de Kallpa (el bot)</span>
          <input className="input" inputMode="tel" value={bot} onChange={(e) => setBot(e.target.value)} placeholder="51 999 999 999" /></label>
        <label className="field"><span>Tu número de WhatsApp</span>
          <input className="input" inputMode="tel" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="51 987 654 321" /></label>
        <div className="row wrap">
          <button className="btn sm" onClick={async () => {
            setBotNumber(bot)
            try {
              await send(`/api/businesses/${bid}`, { name: ctx.business.name, owner_name: ctx.business.owner_name, phone }, 'PATCH')
              ctx.toast('Listo. Ya puedes abrir tu WhatsApp desde Inicio.'); ctx.refresh()
            } catch (e) { ctx.toast((e as Error).message) }
          }}>Guardar</button>
          {botNumber(bot) && <a className="btn sm ghost" href={waLinkFor(botNumber(bot))} target="_blank" rel="noreferrer">Probar: abrir WhatsApp</a>}
        </div>
        {ctx.health?.whatsapp.join_code && botNumber(bot) && (
          <p className="faint" style={{ marginTop: 10 }}>
            Primera vez con este número (Twilio Sandbox): envía <b>{ctx.health.whatsapp.join_code}</b>.{' '}
            <a href={waLinkFor(botNumber(bot), ctx.health.whatsapp.join_code)} target="_blank" rel="noreferrer">Enviarlo ahora</a>
          </p>
        )}
      </div>
      <div className="card">
        <h2>Conexión</h2>
        <KV k="Voz en el servidor" v={h?.transcription.model_on_disk ? 'Lista (faster-whisper)' : h?.transcription.installed ? 'Falta descargar el modelo' : 'No instalada (uso la del celular)'} />
        <KV k="Asistente con IA (agente Women2)" v={h?.agent?.enabled ? `Activo · ${h.agent.model}` : 'Desactivado: uso reglas locales'} />
        <KV k="WhatsApp" v={h?.whatsapp.status ?? '—'} />
        <label className="field" style={{ marginTop: 10 }}><span>Servidor (para la app Android)</span>
          <input className="input" value={api} onChange={(e) => setApi(e.target.value)} placeholder="https://tu-servidor" /></label>
        <button className="btn sm ghost" onClick={() => { setApiBase(api); location.reload() }}>Guardar servidor</button>
      </div>
      <div className="card">
        <h2>Mensajes automáticos</h2>
        <p className="faint" style={{ marginTop: 0 }}>Kallpa te escribe sola, máximo 2 veces al día: en la mañana los avisos (pagos, stock, fiados) y en la noche cómo te fue.
          El domingo, tu semana; el día 1, tu mes. Pruébalos aquí (aparecen en tu chat y se envían por WhatsApp cuando está conectado):</p>
        <div className="row wrap">
          {([['manana', 'Avisos de la mañana'], ['noche', 'Resumen de la noche'], ['semana', 'Resumen del domingo'], ['mes', 'Resumen del día 1']] as const).map(([k, l]) => (
            <button key={k} className="btn sm ghost" onClick={async () => {
              const r = await send<{ text: string }[]>(`/api/businesses/${bid}/notifications/run?slot=${k}`)
              ctx.toast(r.length ? 'Listo: míralo en tu chat.' : 'No hay nada nuevo que avisar.'); ctx.refresh(); if (r.length) ctx.go('chat')
            }}>{l}</button>
          ))}
        </div>
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
