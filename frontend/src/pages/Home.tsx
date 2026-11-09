import { useEffect, useState } from 'react'
import type { Ctx } from '../App'
import { botNumber, fmtDate, get, send, soles, waLinkFor } from '../lib/api'
import { load, save } from '../lib/store'
import type { Dashboard } from '../lib/types'
import { Progress } from '../components/charts'
import { IconArrow, IconChevron, IconMic } from '../components/icons'

function greeting(): string {
  const h = new Date().getHours()
  return h < 12 ? 'Buen día' : h < 19 ? 'Buenas tardes' : 'Buenas noches'
}

type Alert = { ico: string; bg: string; text: string; sub?: string; onClick?: () => void; actions?: JSX.Element }

/** Inicio: responde las 3 preguntas del día. Lo demás está en «Mis números». */
export default function Home({ ctx }: { ctx: Ctx }) {
  const bid = ctx.business.id
  const [d, setD] = useState<Dashboard | null>(() => load<Dashboard | null>(`kallpa.dash.${bid}`, null))
  const [err, setErr] = useState(false)

  useEffect(() => {
    get<Dashboard>(`/api/businesses/${bid}/dashboard`).then((x) => { setD(x); setErr(false); save(`kallpa.dash.${bid}`, x) }).catch(() => setErr(true))
  }, [bid, ctx.tick])

  async function consent(decision: 'si' | 'no') {
    if (!d?.consent.pending_month) return
    await send(`/api/businesses/${bid}/report/consent`, { month: d.consent.pending_month, decision })
    ctx.toast(decision === 'si' ? 'Listo, autorizaste el envío (en esta demo es simulado).' : 'Ok, no se envía este mes.')
    ctx.refresh()
  }

  if (!d) return <div className="empty">{err ? 'Sin conexión y sin datos guardados todavía.' : 'Cargando tu negocio…'}</div>

  const cash = d.cash
  const day = d.day
  const repo = d.goals.find((g) => g.kind === 'reposicion' && g.status === 'activa')
  const restockAvail = repo?.available_cents ?? cash.available_for_restock_cents
  const owner = d.business.owner_name
  const rawDate = new Date(d.today + 'T12:00').toLocaleDateString('es-PE', { weekday: 'long', day: 'numeric', month: 'long' })
  const dateLabel = rawDate.charAt(0).toUpperCase() + rawDate.slice(1)

  const alerts: Alert[] = []
  if (d.consent.pending_month) alerts.push({
    ico: '🏦', bg: 'var(--lav-soft)', text: `Tu informe de ${d.consent.pending_label} está listo`, sub: `¿Lo enviamos a los bancos aliados (${d.consent.banks || 'BCP'}) para que conozcan tu negocio y te ofrezcan productos financieros?`,
    actions: <div className="row" style={{ marginTop: 8 }}><button className="btn sm" onClick={() => consent('si')}>Sí, envíalo</button><button className="btn sm ghost" onClick={() => consent('no')}>No por ahora</button></div>,
  })
  for (const a of d.alerts_today ?? []) alerts.push({
    ico: a.icon, bg: a.icon === '🤝' ? 'var(--good-soft)' : a.icon === '📦' ? 'var(--sand-soft)' : a.icon === '📈' ? 'var(--bad-soft)' : 'var(--lav-soft)',
    text: a.text,
    onClick: a.icon === '📦' ? () => ctx.go('stock') : undefined,
    actions: a.whatsapp_url ? <div className="row" style={{ marginTop: 8 }}><a className="btn sm" href={a.whatsapp_url} target="_blank" rel="noreferrer">Mandar recordatorio por WhatsApp</a></div> : undefined,
  })
  if (d.cobrar_text) alerts.push({ ico: '🤝', bg: 'var(--good-soft)', text: d.cobrar_text, onClick: () => ctx.go('numeros') })
  const lastMsg = d.messages?.find((m) => m.kind !== 'manana')   // los avisos de la mañana ya están en «Para hoy»

  return (
    <div className="wrap">
      <div className="hello">
        <h1>{greeting()}{owner ? `, ${owner}` : ''}</h1>
        <p style={{ textTransform: 'none' }}>{dateLabel}</p>
      </div>
      {err && <div className="banner warn">Sin conexión. Te muestro lo último guardado ({fmtDate(d.updated_at, true)}).</div>}

      <button className="dictate" onClick={() => ctx.go('chat')}>
        <span className="mic-circle"><IconMic /></span>
        <span style={{ flex: 1 }}><b>Dictar una venta o un gasto</b><span>{d.business.kind === 'verduras' ? 'Ej.: «vendí 3 soles de tomate y un kilo de papa»' : 'Ej.: «vendí 3 polos a 20 soles por Yape»'}</span></span>
      </button>
      <div className="grid2" style={{ marginTop: -6, marginBottom: 18 }}>
        {botNumber(ctx.health?.whatsapp.number)
          ? <a className="btn wa-btn" href={waLinkFor(botNumber(ctx.health?.whatsapp.number))} target="_blank" rel="noreferrer">🟢 Abrir mi WhatsApp</a>
          : <button className="btn wa-btn" onClick={() => ctx.go('chat', 'whatsapp')}>🟢 Escribir por WhatsApp</button>}
        <button className="btn ghost" onClick={() => ctx.go('chat', 'cierre')}>🌙 Cerrar mi día</button>
      </div>
      {ctx.health?.whatsapp.join_code && botNumber(ctx.health?.whatsapp.number) && (
        <p className="faint" style={{ marginTop: -10, marginBottom: 16, textAlign: 'center' }}>
          ¿Primera vez? <a href={waLinkFor(botNumber(ctx.health?.whatsapp.number), ctx.health.whatsapp.join_code)} target="_blank" rel="noreferrer">Activa tu WhatsApp con Kallpa</a> (envía «{ctx.health.whatsapp.join_code}»)
        </p>
      )}

      <div className="qcard">
        <div className="qtitle"><span className="num-badge">1</span>¿Cuánto cobré hoy? <span className="faint" style={{ fontWeight: 400 }}>· solo hoy</span></div>
        <div className="answer">{soles(day.collected_cents)}</div>
        <p className="say">{day.sales_count ? `En ${day.sales_count} ${day.sales_count === 1 ? 'venta' : 'ventas'}. Hoy ganaste ${soles(day.profit_cents)}.` : 'Aún no registras ventas hoy.'}</p>
        <div className="chips">
          <span className="chip2">Efectivo <b>{soles(day.collected_by_method.efectivo)}</b></span>
          <span className="chip2">Yape <b>{soles(day.collected_by_method.yape)}</b></span>
          {day.new_credit_cents > 0 && <span className="chip2">Fiado <b>{soles(day.new_credit_cents)}</b></span>}
        </div>
      </div>

      <div className="qcard navy">
        <div className="qtitle"><span className="num-badge">2</span>¿Cuánto tengo en total?</div>
        {cash.complete ? (
          <>
            <div className="answer">{soles(cash.total_cents)}</div>
            <p className="say">Todo lo que tienes juntado: lo de hoy{day.collected_cents ? ` (${soles(day.collected_cents)})` : ''} más lo de días anteriores, menos lo que ya gastaste.</p>
            <div className="chips">
              <span className="chip2">Efectivo <b>{soles(cash.efectivo_cents)}</b></span>
              <span className="chip2">Yape <b>{soles(cash.yape_cents)}</b></span>
              {cash.ahorro_metas_cents > 0 && <span className="chip2">Guardado en metas <b>{soles(cash.ahorro_metas_cents)}</b></span>}
            </div>
          </>
        ) : (
          <>
            <div className="answer" style={{ fontSize: '1.6rem' }}>Cuenta tu plata</div>
            <p className="say">Cuenta la plata que tienes ahora en tu monedero y dímela: desde ahí llevo tu caja.</p>
            <div className="go"><button className="btn sm ghost" onClick={() => ctx.go('chat', 'contar')}>Contar mi plata</button></div>
          </>
        )}
      </div>

      <div className="qcard sand">
        <div className="qtitle"><span className="num-badge">3</span>¿Cuánto puedo usar para reponer?</div>
        {restockAvail === null || restockAvail === undefined ? (
          <p className="say" style={{ marginTop: 8 }}>Primero necesito tu saldo inicial.</p>
        ) : (
          <>
            <div className="answer">{soles(Math.max(0, restockAvail))}</div>
            <p className="say">
              {repo ? (repo.missing_cents ? `Tu próxima compra cuesta ${soles(repo.target_cents)}. Te faltan ${soles(repo.missing_cents)}.` : `Tu próxima compra cuesta ${soles(repo.target_cents)}. ¡Ya te alcanza!`)
                : 'Es tu caja menos lo que tienes que pagar esta semana.'}
            </p>
            {repo && <div style={{ marginTop: 12 }}><Progress pct={repo.progress_pct} accent /></div>}
            {cash.upcoming_payments.length > 0 && (
              <div className="chips">
                {cash.upcoming_payments.map((u, i) => <span key={i} className="chip2">{u.name} {fmtDate(u.due)} <b>{soles(u.amount_cents)}</b></span>)}
              </div>
            )}
            {!repo && <div className="go"><button className="linkbtn" onClick={() => ctx.go('metas')}>Ponerme una meta de reposición <IconArrow /></button></div>}
          </>
        )}
      </div>

      {lastMsg && (
        <>
          <div className="section-title">Último mensaje de Kallpa</div>
          <div className="qcard" style={{ background: 'var(--brand-soft)', borderColor: 'var(--sage-2)' }}>
            <div className="qtitle">💬 {lastMsg.title}</div>
            <p className="say" style={{ marginTop: 8, whiteSpace: 'pre-line', color: 'var(--ink)' }}>{lastMsg.text}</p>
            <p className="faint" style={{ marginBottom: 0 }}>{lastMsg.sent_whatsapp ? 'Enviado por WhatsApp' : 'Se envía por WhatsApp cuando está conectado'} · también está en tu chat</p>
          </div>
        </>
      )}

      {alerts.length > 0 && (
        <>
          <div className="section-title">Para hoy</div>
          <div className="alerts">
            {alerts.map((a, i) => {
              const body = (
                <>
                  <span className="ico" style={{ background: a.bg }}>{a.ico}</span>
                  <span className="txt">{a.text}{a.sub && <small>{a.sub}</small>}{a.actions}</span>
                  {a.onClick && <IconChevron className="chev" />}
                </>
              )
              return a.onClick
                ? <button key={i} className="alert-row" onClick={a.onClick}>{body}</button>
                : <div key={i} className="alert-row">{body}</div>
            })}
          </div>
        </>
      )}

      <button className="btn line block" style={{ marginTop: 20 }} onClick={() => ctx.go('numeros')}>Ver cómo va mi negocio <IconArrow width={18} /></button>
    </div>
  )
}
