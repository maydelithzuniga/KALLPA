import { soles } from '../lib/api'

type FlowRow = { label: string; inflow_cents: number; outflow_cents: number; net_cents: number }

/** Flujo de caja diario: barras de entradas (arriba) y salidas (abajo) con línea de flujo neto acumulado. */
export function FlowChart({ rows, height = 170 }: { rows: FlowRow[]; height?: number }) {
  const W = 520, H = height, padL = 4, padR = 4, mid = H * 0.55
  const maxIn = Math.max(1, ...rows.map((r) => r.inflow_cents))
  const maxOut = Math.max(1, ...rows.map((r) => r.outflow_cents))
  const maxV = Math.max(maxIn, maxOut)
  const upH = mid - 14, downH = H - mid - 18
  const bw = (W - padL - padR) / rows.length
  let acc = 0
  const cum = rows.map((r) => (acc += r.net_cents))
  const cMin = Math.min(0, ...cum), cMax = Math.max(1, ...cum)
  const cy = (v: number) => 10 + (H - 30) * (1 - (v - cMin) / (cMax - cMin || 1))
  const path = cum.map((v, i) => `${i ? 'L' : 'M'}${padL + bw * i + bw / 2},${cy(v)}`).join(' ')
  return (
    <div>
      <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Flujo de caja de los últimos días">
        <line x1={0} x2={W} y1={mid} y2={mid} stroke="var(--line)" />
        {rows.map((r, i) => {
          const x = padL + bw * i + bw * 0.15
          const w = bw * 0.7
          const hi = (r.inflow_cents / maxV) * upH
          const ho = (r.outflow_cents / maxV) * downH
          return (
            <g key={i}>
              <title>{`${r.label}: entró ${soles(r.inflow_cents)}, salió ${soles(r.outflow_cents)}`}</title>
              <rect x={x} y={mid - hi} width={w} height={hi} rx={1.5} fill="var(--chart-in)" />
              <rect x={x} y={mid + 1} width={w} height={ho} rx={1.5} fill="var(--chart-out)" />
              {(i % 7 === 0 && i < rows.length - 3 || i === rows.length - 1) && <text x={x + w / 2} y={H - 3} textAnchor="middle">{r.label}</text>}
            </g>
          )
        })}
        <path d={path} fill="none" stroke="var(--chart-net)" strokeWidth={1.6} strokeDasharray="3 2" />
      </svg>
      <div className="legend">
        <span><i className="dot" style={{ background: 'var(--chart-in)' }} /> Entró</span>
        <span><i className="dot" style={{ background: 'var(--chart-out)' }} /> Salió</span>
        <span><i className="dot" style={{ background: 'var(--chart-net)' }} /> Flujo acumulado: {soles(cum[cum.length - 1] ?? 0)}</span>
      </div>
    </div>
  )
}

export function Columns({ items, height = 120, highlight }: { items: { label: string; value: number; title?: string }[]; height?: number; highlight?: number }) {
  const W = 520, H = height
  const max = Math.max(1, ...items.map((i) => i.value))
  const bw = W / items.length
  return (
    <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img">
      {items.map((it, i) => {
        const h = ((H - 30) * it.value) / max
        return (
          <g key={i}>
            <title>{it.title ?? `${it.label}: ${soles(it.value)}`}</title>
            <rect x={bw * i + bw * 0.18} y={H - 18 - h} width={bw * 0.64} height={h} rx={7}
              fill={highlight === i ? 'var(--brand)' : 'var(--sand)'} />
            <text x={bw * i + bw / 2} y={H - 18 - h - 4} textAnchor="middle" style={{ fontSize: 9 }}>{Math.round(it.value / 100)}</text>
            <text x={bw * i + bw / 2} y={H - 4} textAnchor="middle">{it.label}</text>
          </g>
        )
      })}
    </svg>
  )
}

export function HBars({ items, fmt = soles }: { items: { name: string; value: number | null; note?: string }[]; fmt?: (v: number) => string }) {
  const max = Math.max(1, ...items.map((i) => Math.abs(i.value ?? 0)))
  return (
    <div>
      {items.map((it, i) => (
        <div className="hbar" key={i}>
          <span className="name">{it.name}</span>
          <span className="track"><i style={{ width: `${it.value === null ? 0 : (100 * Math.abs(it.value)) / max}%`, background: it.value !== null && it.value < 0 ? 'var(--bad)' : undefined }} /></span>
          <span className="num small">{it.value === null ? (it.note ?? 'pendiente') : fmt(it.value)}</span>
        </div>
      ))}
    </div>
  )
}

export function Progress({ pct, accent }: { pct: number | null; accent?: boolean }) {
  return <div className={`bar ${accent ? 'accent' : ''}`} role="progressbar" aria-valuenow={pct ?? 0}><i style={{ width: `${Math.max(0, Math.min(100, pct ?? 0))}%` }} /></div>
}

/** Barra apilada: reparto entre partes (ej. efectivo / Yape / fiado). */
export function Stacked({ parts }: { parts: { label: string; value: number; color: string }[] }) {
  const total = parts.reduce((a, p) => a + Math.max(0, p.value), 0) || 1
  return (
    <div>
      <div style={{ display: 'flex', height: 14, borderRadius: 7, overflow: 'hidden', background: 'var(--surface-2)' }}>
        {parts.map((p, i) => <i key={i} title={`${p.label}: ${soles(p.value)}`} style={{ width: `${(100 * Math.max(0, p.value)) / total}%`, background: p.color }} />)}
      </div>
      <div className="legend">
        {parts.map((p, i) => <span key={i}><i className="dot" style={{ background: p.color }} />{p.label} {soles(p.value)}</span>)}
      </div>
    </div>
  )
}
