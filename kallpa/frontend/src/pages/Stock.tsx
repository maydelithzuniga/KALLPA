import { useEffect, useState } from 'react'
import type { Ctx } from '../App'
import { fmtDate, get, send, soles, toCents } from '../lib/api'
import type { CountT, InventoryItem } from '../lib/types'
import { KV, Sheet } from '../components/ui'
import { IconPlus } from '../components/icons'

export default function Stock({ ctx }: { ctx: Ctx }) {
  const bid = ctx.business.id
  const [items, setItems] = useState<InventoryItem[] | null>(null)
  const [rec, setRec] = useState<{ open: (CountT & { text: string })[] } | null>(null)
  const [sel, setSel] = useState<InventoryItem | null>(null)
  const [adding, setAdding] = useState(false)
  const [cashOpen, setCashOpen] = useState(false)

  useEffect(() => {
    get<InventoryItem[]>(`/api/businesses/${bid}/inventory`).then(setItems).catch(() => setItems([]))
    get<{ open: (CountT & { text: string })[] }>(`/api/businesses/${bid}/reconciliation`).then(setRec).catch(() => undefined)
  }, [bid, ctx.tick])

  async function resolve(id: number, action: 'ajustar' | 'pendiente' | 'revisado') {
    await send(`/api/counts/${id}/resolve`, { action })
    ctx.toast(action === 'ajustar' ? 'Stock ajustado al conteo.' : action === 'pendiente' ? 'Lo dejé pendiente de revisar.' : 'Marcado como revisado.')
    ctx.refresh()
  }

  const tracked = items?.filter((i) => i.track_stock) ?? []
  const others = items?.filter((i) => !i.track_stock) ?? []
  const value = tracked.reduce((a, i) => a + (i.stock_value_cents ?? 0), 0)

  return (
    <div>
      <div className="spread" style={{ marginBottom: 10 }}>
        <h1>Mercadería</h1>
        <button className="btn sm" onClick={() => setAdding(true)}><IconPlus width={18} /> Producto</button>
      </div>
      {tracked.length > 0 && (
        <div className="card">
          <div className="grid3">
            <div className="mini"><div className="l">Productos</div><div className="v">{tracked.length}</div></div>
            <div className="mini"><div className="l">Valor a costo</div><div className="v">{soles(value)}</div></div>
            <div className="mini"><div className="l">Por reponer</div><div className="v">{tracked.filter((i) => i.needs_restock).length}</div></div>
          </div>
        </div>
      )}

      {rec && rec.open.length > 0 && (
        <div className="card">
          <h2>Diferencias por revisar</h2>
          {rec.open.map((c) => (
            <div key={c.id} style={{ padding: '8px 0', borderBottom: '1px solid var(--line)' }}>
              <div className="spread"><b>{c.product ?? `Caja ${c.pocket}`}</b>
                <span className={`pill ${c.result === 'diferencia' ? 'bad' : ''}`}>{c.result === 'diferencia' ? 'Con diferencia' : 'Información incompleta'}{c.review_status === 'pendiente' ? ' · pendiente' : ''}</span></div>
              <p className="small" style={{ margin: '4px 0' }}>{c.text}</p>
              {c.hints && <ul className="small muted" style={{ margin: '0 0 6px', paddingLeft: 18 }}>{c.hints.map((h) => <li key={h}>{h}</li>)}</ul>}
              <div className="row wrap">
                {c.kind === 'stock' && <button className="btn sm" onClick={() => resolve(c.id, 'ajustar')}>{c.result === 'diferencia' ? 'Ajustar al conteo' : 'Usar como stock inicial'}</button>}
                {c.review_status !== 'pendiente' && <button className="btn sm ghost" onClick={() => resolve(c.id, 'pendiente')}>Dejar pendiente</button>}
                <button className="btn sm ghost" onClick={() => resolve(c.id, 'revisado')}>Ya lo revisé</button>
              </div>
            </div>
          ))}
        </div>
      )}

      {items === null && <div className="empty">Cargando…</div>}
      {tracked.map((i) => (
        <button key={i.id} className="card" style={{ width: '100%', textAlign: 'left', display: 'block' }} onClick={() => setSel(i)}>
          <div className="spread">
            <div><b>{i.name}</b><div className="faint">{i.price_cents !== null ? `Vendes a ${soles(i.price_cents)}` : 'Sin precio'} · {i.cost_cents !== null ? `cuesta ${soles(i.cost_cents)}` : 'sin costo'}</div></div>
            <div style={{ textAlign: 'right' }}>
              <div className="mid num">{i.expected_stock ?? '—'}</div>
              <div className="faint">{i.expected_stock === null ? 'sin stock inicial' : 'esperado'}</div>
            </div>
          </div>
          <div className="row wrap" style={{ marginTop: 8 }}>
            {i.unit_margin_cents !== null && <span className="pill good">Deja {soles(i.unit_margin_cents)} c/u</span>}
            {i.days_left !== null && <span className={`pill ${i.needs_restock ? 'warn' : ''}`}>Alcanza ~{i.days_left} días</span>}
            {i.needs_restock && <span className="pill accent">Reponer</span>}
            {i.last_count && <span className={`pill ${i.last_count.result === 'consistente' ? 'good' : i.last_count.result === 'diferencia' ? 'bad' : ''}`}>Conteo {fmtDate(i.last_count.counted_at)}</span>}
            {i.needs_review.map((n) => <span key={n} className="pill warn">{n}</span>)}
          </div>
        </button>
      ))}
      {others.length > 0 && (
        <div className="card">
          <h2>{ctx.business.kind === 'reventa' ? 'Otros' : 'Lo que vendes e insumos'}</h2>
          {others.map((i) => (
            <button key={i.id} className="mv" style={{ padding: '8px 0' }} onClick={() => setSel(i)}>
              <span className="body"><b>{i.name}</b><span className="faint">{i.is_input ? 'Insumo' : i.is_service ? 'Servicio' : 'Sin control de stock'}</span></span>
              <span className="amt small">{i.price_cents !== null ? soles(i.price_cents) : i.cost_cents !== null ? `costo ${soles(i.cost_cents)}` : '—'}</span>
            </button>
          ))}
        </div>
      )}

      <div className="card">
        <div className="spread"><div><h2>Contar la caja</h2><p className="faint" style={{ margin: 0 }}>Compara lo que tienes con lo registrado.</p></div>
          <button className="btn sm line" onClick={() => setCashOpen(true)}>Contar</button></div>
      </div>
      <p className="faint">Tip: también puedes decir en el chat «conté 17 polos» o «tengo 300 en efectivo».</p>

      <ProductSheet item={sel} bid={bid} onClose={() => setSel(null)} onSaved={() => { setSel(null); ctx.refresh() }} toast={ctx.toast} />
      <NewProduct open={adding} bid={bid} kind={ctx.business.kind} onClose={() => setAdding(false)} onSaved={() => { setAdding(false); ctx.refresh() }} />
      <CashCount open={cashOpen} bid={bid} onClose={() => setCashOpen(false)} onSaved={() => ctx.refresh()} />
    </div>
  )
}

function ProductSheet({ item, bid, onClose, onSaved, toast }: { item: InventoryItem | null; bid: number; onClose: () => void; onSaved: () => void; toast: (t: string) => void }) {
  const [price, setPrice] = useState('')
  const [cost, setCost] = useState('')
  const [stock, setStock] = useState('')
  const [reorder, setReorder] = useState('')
  const [count, setCount] = useState('')
  const [result, setResult] = useState<(CountT & { text: string }) | null>(null)
  useEffect(() => {
    if (!item) return
    setPrice(item.price_cents !== null ? String(item.price_cents / 100) : '')
    setCost(item.cost_cents !== null ? String(item.cost_cents / 100) : '')
    setStock(''); setCount(''); setResult(null)
    setReorder(item.reorder_point !== null ? String(item.reorder_point) : '')
  }, [item])
  if (!item) return null
  async function save() {
    const body: Record<string, unknown> = { price_cents: price ? toCents(price) : null, cost_cents: cost ? toCents(cost) : null }
    if (reorder) body.reorder_point = parseInt(reorder)
    if (stock && item!.initial_stock === null) body.current_stock = parseInt(stock)
    await send(`/api/products/${item!.id}`, body, 'PATCH')
    toast('Guardado.')
    onSaved()
  }
  async function doCount() {
    const r = await send<CountT & { text: string }>(`/api/businesses/${bid}/counts`, { kind: 'stock', product_id: item!.id, counted: parseInt(count) })
    setResult(r)
  }
  async function resolve(action: 'ajustar' | 'pendiente') {
    if (!result) return
    await send(`/api/counts/${result.id}/resolve`, { action })
    toast(action === 'ajustar' ? 'Stock ajustado.' : 'Pendiente de revisar.')
    onSaved()
  }
  return (
    <Sheet open onClose={onClose} title={item.name}>
      <div className="card flat">
        <KV k="Stock esperado" v={item.expected_stock ?? 'Falta el stock inicial'} />
        <KV k="Vendidos (28 días)" v={`${item.sold_28d} · ${item.daily_avg}/día`} />
        {item.stock_value_cents !== null && <KV k="Valor a costo" v={soles(item.stock_value_cents)} />}
        {item.unit_margin_cents !== null && <KV k="Margen por unidad" v={soles(item.unit_margin_cents)} />}
      </div>
      <div className="grid2">
        <label className="field"><span>Precio de venta (S/)</span><input className="input" inputMode="decimal" value={price} onChange={(e) => setPrice(e.target.value)} /></label>
        <label className="field"><span>Costo de compra (S/)</span><input className="input" inputMode="decimal" value={cost} onChange={(e) => setCost(e.target.value)} /></label>
      </div>
      {item.track_stock && (
        <div className="grid2">
          {item.initial_stock === null && <label className="field"><span>¿Cuántos tienes hoy?</span><input className="input" inputMode="numeric" value={stock} onChange={(e) => setStock(e.target.value)} /></label>}
          <label className="field"><span>Avisar al quedar</span><input className="input" inputMode="numeric" value={reorder} onChange={(e) => setReorder(e.target.value)} placeholder="ej. 8" /></label>
        </div>
      )}
      <button className="btn block" onClick={save}>Guardar</button>
      {item.track_stock && item.initial_stock !== null && (
        <div className="card" style={{ marginTop: 14 }}>
          <h3>Contar ahora</h3>
          <p className="faint" style={{ marginTop: 2 }}>Comparo con lo que dicen tus registros: stock inicial + compras − ventas ± mermas y ajustes.</p>
          <div className="row">
            <input className="input" inputMode="numeric" value={count} onChange={(e) => setCount(e.target.value)} placeholder="Unidades contadas" />
            <button className="btn" disabled={!count} onClick={doCount}>Cruzar</button>
          </div>
          {result && (
            <div className={`banner ${result.result === 'consistente' ? 'info' : 'warn'}`} style={{ marginTop: 10, flexDirection: 'column' }}>
              <span>{result.text}</span>
              {result.result === 'diferencia' && (
                <div className="row"><button className="btn sm" onClick={() => resolve('ajustar')}>Ajustar al conteo</button>
                  <button className="btn sm ghost" onClick={() => resolve('pendiente')}>Dejar pendiente</button></div>
              )}
            </div>
          )}
        </div>
      )}
    </Sheet>
  )
}

function NewProduct({ open, bid, kind, onClose, onSaved }: { open: boolean; bid: number; kind: string; onClose: () => void; onSaved: () => void }) {
  const [name, setName] = useState('')
  const [aliases, setAliases] = useState('')
  const [price, setPrice] = useState('')
  const [cost, setCost] = useState('')
  const [stock, setStock] = useState('')
  async function save() {
    await send(`/api/businesses/${bid}/products`, {
      name, aliases: aliases.split(',').map((a) => a.trim()).filter(Boolean),
      price_cents: price ? toCents(price) : null, cost_cents: cost ? toCents(cost) : null,
      initial_stock: stock ? parseInt(stock) : null, track_stock: kind === 'reventa', is_service: kind === 'servicios',
    })
    setName(''); setAliases(''); setPrice(''); setCost(''); setStock('')
    onSaved()
  }
  return (
    <Sheet open={open} onClose={onClose} title="Nuevo producto">
      <label className="field"><span>Nombre</span><input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="Ej. Polo estampado" /></label>
      <label className="field"><span>Otros nombres que usas (separados por coma)</span><input className="input" value={aliases} onChange={(e) => setAliases(e.target.value)} placeholder="estampado, polito" /></label>
      <div className="grid2">
        <label className="field"><span>Precio de venta (S/)</span><input className="input" inputMode="decimal" value={price} onChange={(e) => setPrice(e.target.value)} /></label>
        <label className="field"><span>Costo de compra (S/)</span><input className="input" inputMode="decimal" value={cost} onChange={(e) => setCost(e.target.value)} /></label>
      </div>
      {kind === 'reventa' && <label className="field"><span>Stock actual (opcional)</span><input className="input" inputMode="numeric" value={stock} onChange={(e) => setStock(e.target.value)} /></label>}
      <button className="btn block" disabled={!name.trim()} onClick={save}>Guardar</button>
    </Sheet>
  )
}

function CashCount({ open, bid, onClose, onSaved }: { open: boolean; bid: number; onClose: () => void; onSaved: () => void }) {
  const [pocket, setPocket] = useState<'efectivo' | 'yape'>('efectivo')
  const [amount, setAmount] = useState('')
  const [res, setRes] = useState<(CountT & { text: string }) | null>(null)
  async function go() {
    const r = await send<CountT & { text: string }>(`/api/businesses/${bid}/counts`, { kind: 'caja', pocket, counted: toCents(amount) })
    setRes(r)
    onSaved()
  }
  return (
    <Sheet open={open} onClose={() => { setRes(null); setAmount(''); onClose() }} title="Contar la caja">
      <div className="seg" style={{ marginBottom: 10 }}>
        <button className={pocket === 'efectivo' ? 'on' : ''} onClick={() => setPocket('efectivo')}>Efectivo</button>
        <button className={pocket === 'yape' ? 'on' : ''} onClick={() => setPocket('yape')}>Yape</button>
      </div>
      <label className="field"><span>¿Cuánto contaste? (S/)</span><input className="input" inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} /></label>
      <button className="btn block" disabled={!amount} onClick={go}>Cruzar con mis registros</button>
      {res && <div className={`banner ${res.result === 'consistente' ? 'info' : 'warn'}`} style={{ marginTop: 10 }}>{res.text}</div>}
    </Sheet>
  )
}
