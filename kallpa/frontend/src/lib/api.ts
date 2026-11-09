// Cliente de la API. En la app Android (Capacitor) se configura la URL del servidor en Ajustes.
const KEY = 'kallpa.apiUrl'

export function apiBase(): string {
  try {
    const saved = localStorage.getItem(KEY)
    if (saved) return saved.replace(/\/$/, '')
  } catch { /* sin almacenamiento */ }
  const env = (import.meta as unknown as { env: Record<string, string> }).env.VITE_API_URL
  return (env || '').replace(/\/$/, '')
}

export function setApiBase(url: string) {
  try { if (url) localStorage.setItem(KEY, url); else localStorage.removeItem(KEY) } catch { /* */ }
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) { super(message); this.status = status }
}

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let msg = res.statusText
    try { const j = await res.json(); msg = j.detail || msg } catch { /* */ }
    throw new ApiError(res.status, typeof msg === 'string' ? msg : JSON.stringify(msg))
  }
  return res.json() as Promise<T>
}

export async function get<T>(path: string): Promise<T> {
  return handle<T>(await fetch(apiBase() + path))
}

export async function send<T>(path: string, body?: unknown, method = 'POST'): Promise<T> {
  return handle<T>(await fetch(apiBase() + path, {
    method, headers: { 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body),
  }))
}

export async function upload<T>(path: string, form: FormData): Promise<T> {
  return handle<T>(await fetch(apiBase() + path, { method: 'POST', body: form }))
}

export function uid(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID()
  return Date.now().toString(36) + Math.random().toString(36).slice(2)
}

export const soles = (cents: number | null | undefined, dec?: boolean): string => {
  if (cents === null || cents === undefined) return 'S/ —'
  const neg = cents < 0
  const abs = Math.abs(cents)
  const showDec = dec ?? abs % 100 !== 0
  const txt = (abs / 100).toLocaleString('es-PE', { minimumFractionDigits: showDec ? 2 : 0, maximumFractionDigits: showDec ? 2 : 0 })
  return `${neg ? '-' : ''}S/ ${txt}`
}

export const fmtDate = (iso: string, withTime = false) => {
  const d = new Date(iso)
  const opts: Intl.DateTimeFormatOptions = { day: 'numeric', month: 'short' }
  if (withTime) { opts.hour = '2-digit'; opts.minute = '2-digit' }
  return d.toLocaleString('es-PE', opts)
}

export const fmtTime = (iso: string) => new Date(iso).toLocaleTimeString('es-PE', { hour: '2-digit', minute: '2-digit' })

export const toCents = (v: string): number | null => {
  const n = parseFloat(v.replace(',', '.'))
  return Number.isFinite(n) ? Math.round(n * 100) : null
}
