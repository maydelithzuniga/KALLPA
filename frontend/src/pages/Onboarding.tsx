import { useEffect, useState } from 'react'
import { get, send } from '../lib/api'
import type { Business, Health } from '../lib/types'
import { IconChat, IconChevron, IconMic } from '../components/icons'

type Props = { health: Health | null; online: boolean; onStart: (b: Business) => void; onPick: (id: number) => void }

const KIND_LABEL: Record<string, string> = { verduras: 'Verdulería', reventa: 'Reventa', comida: 'Comida preparada', servicios: 'Servicios' }

/** Primera pantalla: elegir por dónde conversar. Todo lo demás se arma conversando. */
export default function Onboarding({ health, online, onStart, onPick }: Props) {
  const [list, setList] = useState<Business[] | null>(null)
  const [wa, setWa] = useState(false)
  const [busy, setBusy] = useState(false)
  useEffect(() => { get<Business[]>('/api/businesses').then(setList).catch(() => setList([])) }, [])

  async function startApp() {
    setBusy(true)
    try { onStart(await send<Business>('/api/businesses', { name: 'Mi negocio' })) } finally { setBusy(false) }
  }

  const demos = list?.filter((b) => b.demo && b.setup_state === 'listo') ?? []
  const waNumber = health?.whatsapp.number
  return (
    <div className="wrap" style={{ maxWidth: 560 }}>
      <div className="welcome" style={{ paddingBottom: 22 }}>
        <img src={`${import.meta.env.BASE_URL}icon.svg`} alt="" />
        <h1>Kallpa</h1>
        <p className="muted">Lleva las cuentas de tu negocio hablando, como le mandas audios a una amiga. Vamos a conversar un ratito para conocer tu negocio.</p>
      </div>
      {!online && <div className="banner warn">Sin conexión. Conéctate una vez para empezar.</div>}

      <div className="section-title" style={{ marginTop: 0 }}>¿Por dónde quieres conversar?</div>
      <button className="dictate" onClick={() => setWa(!wa)} style={{ background: '#1f8f4e', boxShadow: '0 10px 24px rgba(31,143,78,.25)' }}>
        <span className="mic-circle"><IconChat /></span>
        <span style={{ flex: 1 }}><b>Por WhatsApp</b><span>Mándale audios a Kallpa desde tu WhatsApp</span></span>
      </button>
      {wa && (
        <div className="qcard" style={{ marginTop: -8 }}>
          {health?.whatsapp.connected && waNumber ? (
            <>
              <p className="say" style={{ marginTop: 0 }}>Escríbele «hola» a Kallpa y te hará unas preguntas para conocer tu negocio.</p>
              {health.whatsapp.join_code && <p className="faint" style={{ marginTop: 0 }}>Primera vez: se enviará «{health.whatsapp.join_code}» para activar el número de prueba. Luego escribe «hola».</p>}
              <a className="btn block" href={`https://wa.me/${waNumber.replace(/\D/g, '')}?text=${encodeURIComponent(health.whatsapp.join_code || 'Hola')}`} target="_blank" rel="noreferrer">Abrir WhatsApp</a>
            </>
          ) : (
            <p className="say" style={{ margin: 0 }}>En esta demo, WhatsApp está <b>pendiente de conectar</b>. Es el mismo asistente que en la app: conversa aquí abajo y funcionará igual cuando se conecte el número.</p>
          )}
        </div>
      )}
      <button className="dictate" onClick={startApp} disabled={busy || !online}>
        <span className="mic-circle"><IconMic /></span>
        <span style={{ flex: 1 }}><b>Aquí en la app</b><span>Te hago unas preguntas y armamos tu negocio juntas</span></span>
      </button>

      {demos.length > 0 && (
        <>
          <div className="section-title">O mira un negocio de ejemplo</div>
          <div className="listbox">
            {demos.map((b) => (
              <button key={b.id} className="lrow" onClick={() => onPick(b.id)}>
                <span className="ico" style={{ fontSize: 22 }}>{b.kind === 'verduras' ? '🥬' : b.kind === 'comida' ? '🍲' : b.kind === 'servicios' ? '✂️' : '👕'}</span>
                <span className="txt"><b>{b.name}</b><small>{KIND_LABEL[b.kind] ?? b.kind} · datos de ejemplo</small></span>
                <IconChevron className="chev" />
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  )
}
