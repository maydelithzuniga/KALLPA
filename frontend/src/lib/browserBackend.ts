// Modo «demo en un link»: corre el backend de Python dentro del navegador con Pyodide.
// Intercepta fetch('/api/...') y lo atiende con browser/webapp.py (mismas reglas que el servidor).
type Handle = (method: string, path: string, query: string, body: string | null) => string
type PyodideAPI = {
  loadPackage: (p: string[]) => Promise<void>
  runPython: (code: string) => unknown
  runPythonAsync: (code: string) => Promise<unknown>
  pyimport: (m: string) => { handle: Handle }
  FS: { mkdirTree: (p: string) => void; writeFile: (p: string, d: string) => void }
}
declare global { interface Window { loadPyodide?: (o: { indexURL: string }) => Promise<PyodideAPI> } }

const realFetch = window.fetch.bind(window)

function overlay() {
  const el = document.createElement('div')
  el.id = 'boot'
  el.innerHTML = `
    <div class="boot-card">
      <img src="./icon.svg" alt="" width="64" height="64" />
      <b>Preparando la demo de Kallpa</b>
      <span id="boot-status">Cargando el motor…</span>
      <div class="boot-bar"><i id="boot-bar"></i></div>
      <small>Todo corre en tu navegador con datos de demostración. La primera carga tarda unos segundos.</small>
    </div>`
  const st = document.createElement('style')
  st.textContent = `#boot{position:fixed;inset:0;z-index:100;display:grid;place-items:center;background:var(--bg,#f1f6f4);padding:16px}
  .boot-card{background:var(--surface,#fff);border:1px solid var(--line,#e1eae6);border-radius:22px;padding:28px 24px;max-width:360px;width:100%;text-align:center;display:flex;flex-direction:column;align-items:center;gap:10px;color:var(--ink,#17384a)}
  .boot-card img{border-radius:18px}.boot-card span{color:var(--ink-2,#557080);font-size:.92rem}.boot-card small{color:var(--ink-3,#8a9da6);font-size:.8rem}
  .boot-bar{width:100%;height:8px;border-radius:8px;background:var(--surface-2,#f4f8f6);overflow:hidden}.boot-bar i{display:block;height:100%;width:8%;background:var(--brand,#22867a);transition:width .4s}`
  document.head.appendChild(st)
  document.body.appendChild(el)
}
function status(t: string, pct: number) {
  const s = document.getElementById('boot-status'); if (s) s.textContent = t
  const b = document.getElementById('boot-bar'); if (b) b.style.width = `${pct}%`
}
function loadScript(src: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const s = document.createElement('script'); s.src = src; s.onload = () => resolve(); s.onerror = () => reject(new Error('No cargó ' + src))
    document.head.appendChild(s)
  })
}

let ready: Promise<Handle> | null = null

export function startBrowserBackend() {
  overlay()
  ready = (async () => {
    const base = new URL('./py/', location.href).href
    await loadScript(base + 'pyodide.js')
    status('Iniciando Python…', 25)
    const py = await window.loadPyodide!({ indexURL: base })
    status('Instalando la base de datos…', 50)
    await py.loadPackage(['sqlalchemy', 'tzdata'])
    const src: Record<string, string> = await (await realFetch(base + 'app.json')).json()
    py.FS.mkdirTree('/home/pyodide/kallpa/app')
    for (const [name, code] of Object.entries(src)) py.FS.writeFile(`/home/pyodide/kallpa/${name}`, code)
    py.runPython(`import os, sys
os.environ['DATABASE_URL'] = 'sqlite:////home/pyodide/kallpa.db'
os.environ['SEED_DEMO'] = 'false'
sys.path.insert(0, '/home/pyodide/kallpa')`)
    status('Creando datos de demostración…', 70)
    await new Promise((r) => setTimeout(r, 30))
    await py.runPythonAsync('import webapp\nwebapp.boot()')
    status('¡Listo!', 100)
    setTimeout(() => document.getElementById('boot')?.remove(), 250)
    return py.pyimport('webapp').handle
  })()
  ready.catch((e) => status('No se pudo iniciar la demo en este navegador: ' + (e?.message ?? e), 100))

  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const raw = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
    const url = new URL(raw, location.href)
    // Los paquetes de Python se publican con extensión .wasm (el hosting no sirve .zip/.whl)
    if (/\/py\/[^/]+\.(zip|whl)$/.test(url.pathname)) return realFetch(url.href + '.wasm', init)
    const i = url.pathname.indexOf('/api/')
    if (i < 0) return realFetch(input, init)
    const handle = await ready!
    const method = (init?.method || 'GET').toUpperCase()
    const body = typeof init?.body === 'string' ? init.body : init?.body ? '{}' : null
    const q = JSON.stringify(Object.fromEntries(url.searchParams.entries()))
    const res = JSON.parse(handle(method, url.pathname.slice(i), q, body))
    return new Response(JSON.stringify(res.body), { status: res.status, headers: { 'Content-Type': 'application/json' } })
  }
}

export const isBrowserDemo = () => (import.meta as unknown as { env: Record<string, string> }).env.VITE_STATIC === '1'
