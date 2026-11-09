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
