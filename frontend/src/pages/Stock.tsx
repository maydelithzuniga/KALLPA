import { useEffect, useState } from 'react'
import type { Ctx } from '../App'
import { get, send, soles, toCents } from '../lib/api'
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
  const value = tracked.reduce((a, i) => a + (i.stock_value_cents ?? 0), 0)

  const status = (i: InventoryItem) => {
    if (!i.track_stock) return { t: 'Sin control de stock', c: '' }
    if (i.expected_stock === null) return { t: 'Falta tu stock', c: 'warn' }
    if (i.last_count?.result === 'diferencia' && !['ajustado', 'revisado'].includes(i.last_count.review_status)) return { t: 'Revisar conteo', c: 'bad' }
    if (i.needs_restock) return { t: 'Reponer pronto', c: 'accent' }
    return { t: 'En orden', c: 'good' }
  }
  return (
    <div className="wrap">
      <div className="hello spread" style={{ alignItems: 'flex-end' }}>
        <div><h1>Mercadería</h1><p style={{ textTransform: 'none' }}>Tu lista se armó con lo que conversamos. Toca un producto para contarlo, cambiar su precio o ver su ficha.</p></div>
        <button className="btn sm" onClick={() => setAdding(true)}><IconPlus width={18} /> Agregar</button>
      </div>

      {rec && rec.open.length > 0 && (
        <div className="qcard" style={{ borderColor: 'var(--bad-soft)' }}>
          <div className="qtitle">⚠️ Algo no cuadra</div>
          {rec.open.slice(0, 3).map((c) => (
            <div key={c.id} style={{ padding: '12px 0', borderBottom: '1px solid var(--line)' }}>
              <p style={{ margin: '0 0 8px' }}>{c.text}</p>
              <div className="row wrap">
                {c.kind === 'stock' && <button className="btn sm" onClick={() => resolve(c.id, 'ajustar')}>{c.result === 'diferencia' ? 'Corregir al conteo' : 'Usar como stock inicial'}</button>}
                {c.review_status !== 'pendiente' && <button className="btn sm ghost" onClick={() => resolve(c.id, 'pendiente')}>Revisar después</button>}
                <button className="btn sm ghost" onClick={() => resolve(c.id, 'revisado')}>Ya lo revisé</button>
              </div>
            </div>
          ))}
        </div>
      )}

      {items === null && <div className="empty">Cargando…</div>}
      {items && items.length > 0 && (
        <div className="qcard" style={{ padding: 0, overflow: 'hidden' }}>
          <div className="scroll" style={{ overflowX: 'auto' }}>
            <table className="inv-table">
              <thead><tr><th>Producto</th><th>Lo vendes</th><th>Te cuesta</th><th>Lo compras</th><th className="n">Te queda</th></tr></thead>
              <tbody>
                {items.map((i) => {
                  const st = status(i)
                  const u = i.spec_text?.base ?? i.unit
                  const uTxt = u === 'kg' ? 'kg' : u === 'unidad' ? '' : u
                  return (
                    <tr key={i.id} onClick={() => setSel(i)}>
                      <td><b>{i.name}</b><div><span className={`pill ${st.c}`} style={{ marginTop: 4 }}>{st.t}</span></div></td>
                      <td>{i.spec_text?.vende ?? (i.price_cents !== null ? soles(i.price_cents) : '—')}</td>
                      <td>{i.cost_cents !== null ? `${soles(i.cost_cents)}${uTxt ? ` / ${uTxt}` : ''}` : '—'}</td>
                      <td>{i.spec_text?.compra ?? '—'}</td>
                      <td className="n"><b>{i.expected_stock ?? '—'}</b>{i.expected_stock !== null && uTxt ? ` ${uTxt}` : ''}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
      {value > 0 && <p className="faint" style={{ margin: '-4px 0 16px' }}>Lo que te queda vale {soles(value)} a precio de compra.</p>}

      <button className="btn ghost block" onClick={() => setCashOpen(true)}>Contar mi caja</button>
      <p className="faint" style={{ textAlign: 'center' }}>También puedes decir en Dictar: «conté 17 polos».</p>

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
      <details style={{ marginTop: 12 }}>
        <summary className="faint" style={{ cursor: 'pointer' }}>Ver ficha del producto (JSON)</summary>
        <pre className="json">{JSON.stringify({ nombre: item.name, alias: item.aliases, ...item.spec }, null, 2)}</pre>
      </details>
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
