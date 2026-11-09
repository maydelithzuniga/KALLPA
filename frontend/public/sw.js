/* Service worker de Kallpa: abre la interfaz sin conexión después de la primera carga. */
const VERSION = 'kallpa-v1'
const SHELL = ['/', '/index.html', '/manifest.webmanifest', '/icon.svg', '/icon-192.png', '/icon-512.png']

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(VERSION).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()))
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  )
})

self.addEventListener('fetch', (event) => {
  const req = event.request
  if (req.method !== 'GET') return
  const url = new URL(req.url)
  if (url.origin !== self.location.origin) return
  // API: red primero, copia en caché para ver los últimos datos sin señal
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(
      fetch(req).then((res) => {
        if (res.ok) { const copy = res.clone(); caches.open(VERSION).then((c) => c.put(req, copy)) }
        return res
      }).catch(() => caches.match(req).then((r) => r || new Response(JSON.stringify({ offline: true }), { status: 503, headers: { 'Content-Type': 'application/json' } }))),
    )
    return
  }
  // Navegación: red primero, si no hay señal usa la app guardada
  if (req.mode === 'navigate') {
    event.respondWith(fetch(req).then((res) => {
      const copy = res.clone(); caches.open(VERSION).then((c) => c.put('/index.html', copy)); return res
    }).catch(() => caches.match('/index.html')))
    return
  }
  // Archivos estáticos: caché primero
  event.respondWith(
    caches.match(req).then((cached) => cached || fetch(req).then((res) => {
      if (res.ok) { const copy = res.clone(); caches.open(VERSION).then((c) => c.put(req, copy)) }
      return res
    })),
  )
})
