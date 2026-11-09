import { useEffect, type ReactNode } from 'react'

export function Sheet({ open, onClose, children, title }: { open: boolean; onClose: () => void; children: ReactNode; title?: string }) {
  useEffect(() => {
    if (!open) return
    const h = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [open, onClose])
  if (!open) return null
  return (
    <div className="sheet-bg" onClick={onClose}>
      <div className="sheet" onClick={(e) => e.stopPropagation()} role="dialog" aria-label={title}>
        <div className="handle" />
        {title && <h2 style={{ marginBottom: 12 }}>{title}</h2>}
        {children}
      </div>
    </div>
  )
}

export function Toast({ text, onDone }: { text: string | null; onDone: () => void }) {
  useEffect(() => {
    if (!text) return
    const t = setTimeout(onDone, 3200)
    return () => clearTimeout(t)
  }, [text, onDone])
  return text ? <div className="toast" role="status">{text}</div> : null
}

export function KV({ k, v }: { k: ReactNode; v: ReactNode }) {
  return <div className="kv"><span>{k}</span><span>{v}</span></div>
}

export const methodPill = (m: string | null) =>
  m === 'yape' ? <span className="pill yape">Yape</span> : m === 'efectivo' ? <span className="pill cash">Efectivo</span> : null

export const checkPill = (c: string | null, label?: string | null) =>
  c === 'consistente' ? <span className="pill good">{label ?? 'Consistente'}</span>
    : c === 'diferencia' ? <span className="pill bad">{label ?? 'Con diferencia'}</span>
      : c ? <span className="pill">{label ?? 'Sin datos suficientes'}</span> : null

export const originPill = (o: string, label: string) =>
  o === 'respaldo_yape' ? <span className="pill yape">{label}</span>
    : o === 'comprobante' ? <span className="pill good">{label}</span>
      : o === 'con_adjunto' ? <span className="pill warn">{label}</span>
        : <span className="pill">{label}</span>

export type Tone = 'mint' | 'lav' | 'sand' | 'lilac'

/** Tarjeta con franja de color arriba (círculos e ícono), etiqueta, título, texto y pie con píldora y acción. */
export function Tile({ tone, top, eyebrow, title, text, pill, action, onClick, children }: {
  tone: Tone; top: ReactNode; eyebrow?: ReactNode; title: ReactNode; text?: ReactNode; pill?: ReactNode
  action?: ReactNode; onClick?: () => void; children?: ReactNode
}) {
  const Tag = onClick ? 'button' : 'div'
  return (
    <Tag className={`tile ${onClick ? 'clickable' : ''}`} onClick={onClick}>
      <div className={`tile-top ${tone}`}><span className="c1" /><span className="c2" />{top}</div>
      <div className="tile-body">
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h3 className="tile-title">{title}</h3>
        {text && <div className="tile-text">{text}</div>}
        {children}
        {(pill || action) && <div className="tile-foot">{pill ? <span className="tag">{pill}</span> : <span />}{action && <span className="tile-action">{action}</span>}</div>}
      </div>
    </Tag>
  )
}

export function PageHead({ title, sub, right }: { title: ReactNode; sub?: ReactNode; right?: ReactNode }) {
  return (
    <div className="page-head">
      <div><h1>{title}</h1>{sub && <p>{sub}</p>}</div>
      {right}
    </div>
  )
}

export function Strip({ icon, left, right }: { icon?: ReactNode; left: ReactNode; right?: ReactNode }) {
  return <div className="strip"><span className="row" style={{ gap: 10 }}>{icon}{left}</span>{right && <b>{right}</b>}</div>
}
