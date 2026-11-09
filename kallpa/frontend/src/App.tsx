import { useCallback, useEffect, useState } from 'react'
import { get } from './lib/api'
import { load, save, useOnline } from './lib/store'
import type { Business, Health } from './lib/types'
import { IconArrow, IconBox, IconDoc, IconGear, IconHome, IconList, IconMic, IconMore, IconTarget, IconWifiOff } from './components/icons'
import { Toast } from './components/ui'
import Onboarding from './pages/Onboarding'
import Chat from './pages/Chat'
import Home from './pages/Home'
import Stock from './pages/Stock'
import Goals from './pages/Goals'
import More from './pages/More'

export type Tab = 'inicio' | 'chat' | 'stock' | 'metas' | 'mas'
export type Ctx = {
  business: Business; health: Health | null; online: boolean; tick: number; refresh: () => void
  toast: (t: string) => void; go: (t: Tab, sub?: string) => void; sub: string | null; switchBusiness: () => void
}

const SUB_LABEL: Record<string, string> = { historial: 'Historial', reporte: 'Reporte para el banco', ajustes: 'Ajustes' }
const TAB_LABEL: Record<Tab, string> = { inicio: 'Inicio', chat: 'Dictar', stock: 'Mercadería', metas: 'Metas', mas: 'Más' }

export default function App() {
  const online = useOnline()
  const [businessId, setBusinessId] = useState<number | null>(() => load<number | null>('kallpa.business', null))
  const [business, setBusiness] = useState<Business | null>(null)
  const [health, setHealth] = useState<Health | null>(null)
  const [tab, setTab] = useState<Tab>(() => load<Tab>('kallpa.tab', 'inicio'))
  const [sub, setSub] = useState<string | null>(null)
  const [tick, setTick] = useState(0)
  const [toastText, setToast] = useState<string | null>(null)
  const refresh = useCallback(() => setTick((t) => t + 1), [])

  useEffect(() => { get<Health>('/api/health').then(setHealth).catch(() => undefined) }, [online])
  useEffect(() => {
    if (businessId === null) { setBusiness(null); return }
    const cached = load<Business | null>(`kallpa.biz.${businessId}`, null)
    if (cached) setBusiness(cached)
    get<Business>(`/api/businesses/${businessId}`).then((b) => { setBusiness(b); save(`kallpa.biz.${businessId}`, b) })
      .catch((e) => { if (e?.status === 404) { setBusinessId(null); save('kallpa.business', null) } })
  }, [businessId, tick])

  const choose = (id: number | null) => { setBusinessId(id); save('kallpa.business', id); setTab('inicio') }
  const go = (t: Tab, s?: string) => { setTab(t); setSub(s ?? null); save('kallpa.tab', t); window.scrollTo(0, 0) }

  if (!business || business.setup_state !== 'listo') {
    return (
      <div className="app">
        <div className="shell">
          <main className="main">
            <Onboarding business={business} health={health} online={online} onReady={(b) => { setBusiness(b); choose(b.id); refresh() }}
              onPick={(id) => choose(id)} />
          </main>
        </div>
        <Toast text={toastText} onDone={() => setToast(null)} />
      </div>
    )
  }

  const ctx: Ctx = { business, health, online, tick, refresh, toast: setToast, go, sub, switchBusiness: () => choose(null) }
  const tabs: { id: Tab; label: string; icon: JSX.Element }[] = [
    { id: 'inicio', label: 'Inicio', icon: <IconHome /> },
    { id: 'stock', label: 'Mercadería', icon: <IconBox /> },
    { id: 'chat', label: 'Dictar', icon: <IconMic /> },
    { id: 'metas', label: 'Metas', icon: <IconTarget /> },
    { id: 'mas', label: 'Más', icon: <IconMore /> },
  ]
  const side: { id: Tab; sub?: string; label: string; icon: JSX.Element }[] = [
    { id: 'inicio', label: 'Inicio', icon: <IconHome /> },
    { id: 'chat', label: 'Dictar', icon: <IconMic /> },
    { id: 'stock', label: 'Mercadería', icon: <IconBox /> },
    { id: 'metas', label: 'Metas', icon: <IconTarget /> },
    { id: 'mas', sub: 'historial', label: 'Historial', icon: <IconList /> },
    { id: 'mas', sub: 'reporte', label: 'Reporte', icon: <IconDoc /> },
    { id: 'mas', sub: 'ajustes', label: 'Ajustes', icon: <IconGear /> },
  ]
  const initials = (business.owner_name || business.name).split(/\s+/).map((w) => w[0]).join('').slice(0, 2).toUpperCase()
  const crumb = tab === 'mas' && sub ? SUB_LABEL[sub] : TAB_LABEL[tab]

  return (
    <div className="app">
      <aside className="sidebar no-print" aria-label="Menú">
        <div className="brand">
          <img src="/icon.svg" alt="" />
          <div><b>Kallpa</b><span>Tus números, en calma</span></div>
        </div>
        {side.map((s) => (
          <button key={s.label} className={`navlink ${tab === s.id && (s.sub ? sub === s.sub : !(s.id === 'mas' && sub)) ? 'active' : ''}`}
            onClick={() => go(s.id, s.sub)}>
            {s.icon}<span>{s.label}</span>
          </button>
        ))}
        <div className="side-card">
          {business.demo && <span className="pill good dotted" style={{ marginBottom: 8 }}>Modo demostración</span>}
          <div>{business.name}</div>
          <div className="faint">{business.demo ? 'Datos ficticios para la presentación.' : 'Tus datos se guardan en tu servidor.'}</div>
          <button className="linkbtn" onClick={() => choose(null)}>Cambiar de negocio <IconArrow /></button>
        </div>
      </aside>

      <div className="shell">
        <header className="topbar no-print">
          <img className="logo-sm" src="/icon.svg" alt="" />
          <div className="crumb">{business.name} <span style={{ margin: '0 6px' }}>/</span><b>{crumb}</b></div>
          {business.demo && <span className="pill good dotted">Datos de demostración</span>}
          {!online && <span className="pill warn"><IconWifiOff width={14} height={14} /> Sin señal</span>}
          <div className="avatar" title={business.owner_name ?? business.name}>{initials}</div>
        </header>
        <main className={`main ${tab === 'chat' ? 'chat-main' : ''}`}>
          {tab === 'inicio' && <Home ctx={ctx} />}
          {tab === 'chat' && <Chat ctx={ctx} />}
          {tab === 'stock' && <Stock ctx={ctx} />}
          {tab === 'metas' && <Goals ctx={ctx} />}
          {tab === 'mas' && <More ctx={ctx} />}
        </main>
      </div>

      <nav className="tabs no-print" aria-label="Secciones">
        <div className="tabs-inner">
          {tabs.map((t) => (
            <button key={t.id} className={`tab ${tab === t.id ? 'active' : ''} ${t.id === 'chat' ? 'mic-tab' : ''}`} onClick={() => go(t.id)}>
              {t.id === 'chat' ? <span className="bubble">{t.icon}</span> : t.icon}
              <span>{t.label}</span>
            </button>
          ))}
        </div>
      </nav>
      <Toast text={toastText} onDone={() => setToast(null)} />
    </div>
  )
}
