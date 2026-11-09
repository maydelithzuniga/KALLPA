// Cola de envíos pendientes en IndexedDB: audios y textos grabados sin conexión.
// Cada elemento tiene un message_id único: el servidor lo procesa una sola vez aunque se reintente.
export type OutboxItem = {
  id: string            // message_id
  businessId: number
  kind: 'audio' | 'text'
  channel?: 'web' | 'whatsapp'
  blob?: Blob
  mime?: string
  text?: string
  opId?: string
  recordedAt: string
  attempts: number
  lastError?: string
}

const DB = 'kallpa'
const STORE = 'outbox'

function open(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB, 1)
    req.onupgradeneeded = () => { req.result.createObjectStore(STORE, { keyPath: 'id' }) }
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
}

async function tx<T>(mode: IDBTransactionMode, fn: (s: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  const db = await open()
  return new Promise((resolve, reject) => {
    const t = db.transaction(STORE, mode)
    const r = fn(t.objectStore(STORE))
    r.onsuccess = () => resolve(r.result)
    r.onerror = () => reject(r.error)
  })
}

export const outbox = {
  async put(item: OutboxItem) { try { await tx('readwrite', (s) => s.put(item)) } catch { memory.set(item.id, item) } },
  async remove(id: string) { try { await tx('readwrite', (s) => s.delete(id)) } catch { /* */ } memory.delete(id) },
  async all(): Promise<OutboxItem[]> {
    try {
      const items = await tx<OutboxItem[]>('readonly', (s) => s.getAll() as IDBRequest<OutboxItem[]>)
      return [...items, ...memory.values()].sort((a, b) => a.recordedAt.localeCompare(b.recordedAt))
    } catch { return [...memory.values()] }
  },
}
// respaldo en memoria si IndexedDB está bloqueado (ventana privada)
const memory = new Map<string, OutboxItem>()
