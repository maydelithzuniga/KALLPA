import { useEffect, useState } from 'react'
import type { Ctx } from '../App'
import { fmtDate, fmtTime, get, send, soles } from '../lib/api'
import { load, save } from '../lib/store'
import type { Dashboard, Period } from '../lib/types'
import { speak } from '../lib/voice'
import { Columns, FlowChart, HBars, Progress, Stacked } from '../components/charts'
import { IconArrow, IconBox, IconMic, IconSpark, IconSpeaker, IconWallet } from '../components/icons'

function greeting(): string {
  const h = new Date().getHours()
  return h < 12 ? 'Buen día' : h < 19 ? 'Buenas tardes' : 'Buenas noches'
}

export default function Home({ ctx }: { ctx: Ctx }) {
  const bid = ctx.business.id
  const [d, setD] = useState<Dashboard | null>(() => load<Dashboard | null>(`kallpa.dash.${bid}`, null))
  const [err, setErr] = useState(false)
  const [period, setPeriod] = useState<'day' | 'week' | 'month'>('day')

  useEffect(() => {
    get<Dashboard>(`/api/businesses/${bid}/dashboard`).then((x) => { setD(x); setErr(false); save(`kallpa.dash.${bid}`, x) }).catch(() => setErr(true))
  }, [bid, ctx.tick])

  async function consent(decision: 'si' | 'no') {
    if (!d?.consent.pending_month) return
    await send(`/api/businesses/${bid}/report/consent`, { month: d.consent.pending_month, decision })
    ctx.toast(decision === 'si' ? 'Autorizaste el envío (simulado en esta demo).' : 'Ok, no se envía.')
    ctx.refresh()
  }

  if (!d) return <div className="empty">{err ? 'Sin conexión y sin datos guardados todavía.' : 'Cargando tu negocio…'}</div>

  const p: Period = d[period]
  const reposicion = d.goals.find((g) => g.kind === 'reposicion' && g.status === 'activa')
  const ahorro = d.goals.filter((g) => g.kind === 'ahorro' && g.status === 'activa')
  const cash = d.cash
  const periodLabel = { day: 'hoy', week: 'esta semana', month: 'este mes' }[period]
  const withMargin = d.margins.filter((m) => m.margin_pct !== null)
  const marginPct = withMargin.length ? Math.round(withMargin.reduce((a, m) => a + (m.margin_cents ?? 0), 0) / Math.max(1, withMargin.reduce((a, m) => a + m.revenue_cents, 0)) * 100) : null
  const owner = d.business.owner_name
  const todayLabel = new Date(d.today + 'T12:00').toLocaleDateString('es-PE', { weekday: 'long', day: 'numeric', month: 'long' })

  const cashCard = (
    <div className="navy-card">
      <div className="ring" />
      <div className="spread" style={{ position: 'relative' }}>
        <span className="row" style={{ gap: 8 }}><IconWallet width={20} height={20} /> Mi caja</span>
        <span className="chip">Efectivo + Yape</span>
      </div>
      <div className="lbl" style={{ marginTop: 18, position: 'relative' }}>¿Cuánto tengo registrado?</div>
      {cash.complete ? (
        <>
          <div className="amount num" style={{ position: 'relative' }}>{soles(cash.total_cents, true)}</div>
          <div className="row-split">
            <div>Efectivo<b>{soles(cash.efectivo_cents)}</b></div>
            <div>Yape<b>{soles(cash.yape_cents)}</b></div>
            <div>Separado metas<b>{soles(cash.ahorro_metas_cents)}</b></div>
          </div>
          <div className="spread" style={{ marginTop: 16, position: 'relative' }}>
            <span className="lbl">Te deben {soles(cash.receivables_cents)}</span>
            <button className="ghost-link" onClick={() => ctx.go('stock')}>Contar caja <IconArrow width={16} /></button>
          </div>
        </>
      ) : (
        <>
          <div className="amount num" style={{ position: 'relative', fontSize: '1.9rem' }}>{soles(cash.total_cents)}</div>
          <div className="lbl" style={{ position: 'relative' }}>Flujo registrado desde que empezaste</div>
          <div className="warnline">{cash.missing_text}</div>
          <div style={{ marginTop: 14, position: 'relative' }}>
            <button className="ghost-link" onClick={() => ctx.go('mas', 'ajustes')}>Poner saldo inicial <IconArrow width={16} /></button>
          </div>
        </>
      )}
    </div>
  )

  const restockCard = (
    <div className="sand-card">
      <div className="row" style={{ gap: 12 }}>
        <span className="icon-box"><IconBox width={22} height={22} /></span>
        <h2 style={{ margin: 0 }}>¿Cuánto puedo usar para reponer?</h2>
      </div>
      {reposicion ? (
        <>
          <div className="big num">{reposicion.available_cents !== null && reposicion.available_cents !== undefined ? soles(Math.max(0, reposicion.available_cents)) : '—'}</div>
          <p className="muted" style={{ margin: '8px 0 14px' }}>{reposicion.message}</p>
          <Progress pct={reposicion.progress_pct} accent />
        </>
      ) : cash.available_for_restock_cents !== null ? (
        <>
          <div className="big num">{soles(Math.max(0, cash.available_for_restock_cents))}</div>
          <p className="muted" style={{ margin: '8px 0 10px' }}>Tu caja menos los pagos de los próximos 7 días.</p>
          <button className="linkbtn" onClick={() => ctx.go('metas')}>Crear meta de reposición <IconArrow /></button>
        </>
      ) : <p className="muted">{cash.missing_text}</p>}
      {cash.upcoming_payments.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <div className="eyebrow">Pagos que vienen · 7 días</div>
          {cash.upcoming_payments.map((u, i) => <div className="kv" key={i}><span>{u.name} · {fmtDate(u.due)}</span><span>{soles(u.amount_cents)}</span></div>)}
        </div>
      )}
    </div>
  )

  return (
    <div>
      <div className="greet">
        <h1>{greeting()}{owner ? `, ${owner}` : ''} ☀︎</h1>
        <p>Tu negocio se mueve. Tú decides cómo.</p>
      </div>

      {err && <div className="banner warn">Sin conexión. Te muestro lo último guardado ({fmtDate(d.updated_at, true)}).</div>}
      {d.consent.pending_month && (
        <div className="banner info">
          <div className="grow"><b>Tu informe de {d.consent.pending_label} está listo.</b><br /><span className="muted">¿Quieres que se le envíe al BCP?</span></div>
          <div className="row">
            <button className="btn sm" onClick={() => consent('si')}>Sí, envíalo</button>
            <button className="btn sm ghost" onClick={() => consent('no')}>No por ahora</button>
          </div>
        </div>
      )}

      <div className="home-grid">
        <div>
          <section className="hero">
            <svg className="art" viewBox="0 0 200 220" aria-hidden="true">
              <path d="M150 230 V150 Q150 110 110 110 H70 Q40 110 40 80 V-10" fill="none" stroke="var(--sage-2)" strokeWidth="34" strokeLinecap="round" />
              <path d="M150 230 V150 Q150 110 110 110 H70 Q40 110 40 80 V-10" fill="none" stroke="var(--surface)" strokeWidth="2.5" strokeDasharray="7 8" opacity=".8" />
              <circle cx="150" cy="175" r="11" fill="var(--sage)" stroke="var(--sage-3)" strokeWidth="4" />
              <g transform="translate(118 40) rotate(-12)">
                <rect width="58" height="40" rx="10" fill="var(--sage-3)" />
                <rect x="8" y="8" width="42" height="14" rx="4" fill="var(--sage)" />
                <circle cx="29" cy="31" r="4" fill="var(--sage)" />
              </g>
            </svg>
            <div className="eyebrow" style={{ position: 'relative' }}>Tu día · {todayLabel}</div>
            <h2 style={{ position: 'relative' }}>Vendiste {soles(d.day.sales_cents)}.<br />Ganaste {soles(d.day.profit_cents)}.</h2>
            <p style={{ position: 'relative' }}>{d.daily_text}</p>
            <button className="askbox" onClick={() => ctx.go('chat')}>
              <IconMic /><span>¿Qué vendiste o gastaste? Díctalo aquí</span><IconArrow />
            </button>
            <div className="row" style={{ marginTop: 12, position: 'relative' }}>
              <button className="linkbtn" onClick={() => speak(d.daily_text)}><IconSpeaker /> Escuchar resumen</button>
              <span className="faint" style={{ marginLeft: 'auto' }}>Actualizado {fmtTime(d.updated_at)}</span>
            </div>
          </section>

          <div className="only-mobile">{cashCard}</div>

          <div className="card">
            <div className="eyebrow">¿Cuánto cobré hoy?</div>
            <div className="big num">{soles(d.day.collected_cents)}</div>
            <div className="split">
              <div className="mini"><div className="l">Efectivo</div><div className="v">{soles(d.day.collected_by_method.efectivo)}</div></div>
              <div className="mini"><div className="l">Yape</div><div className="v" style={{ color: 'var(--yape)' }}>{soles(d.day.collected_by_method.yape)}</div></div>
              <div className="mini"><div className="l">Fiado hoy</div><div className="v">{soles(d.day.new_credit_cents)}</div></div>
            </div>
            <p className="faint" style={{ margin: '12px 0 0' }}>Vendiste {soles(d.day.sales_cents)} en {d.day.sales_count} ventas{d.day.discounts_cents ? `, con ${soles(d.day.discounts_cents)} de descuentos` : ''}. En total te deben {soles(cash.receivables_cents)}.</p>
          </div>

          <div className="only-mobile">{restockCard}</div>

          <div className="card">
            <div className="card-head"><h2>Cómo va tu negocio</h2></div>
            <div className="seg" style={{ marginBottom: 14 }}>
              {(['day', 'week', 'month'] as const).map((k) => <button key={k} className={period === k ? 'on' : ''} onClick={() => setPeriod(k)}>{{ day: 'Hoy', week: 'Semana', month: 'Mes' }[k]}</button>)}
            </div>
            <div className="grid2">
              <div className="mini"><div className="l">Vendiste {periodLabel}</div><div className="v">{soles(p.sales_cents)}</div></div>
              <div className="mini"><div className="l">Ganancia{p.profit_estimated ? ' (aprox.)' : ''}</div><div className="v" style={{ color: p.profit_cents >= 0 ? 'var(--good)' : 'var(--bad)' }}>{soles(p.profit_cents)}</div></div>
              <div className="mini"><div className="l">Flujo de caja negocio</div><div className="v">{soles(p.business_cashflow_cents)}</div></div>
              <div className="mini"><div className="l">Costo de lo vendido</div><div className="v">{soles(p.cogs_cents)}</div></div>
              <div className="mini"><div className="l">Gastos del negocio</div><div className="v">{soles(p.business_expenses_total_cents)}</div></div>
              <div className="mini"><div className="l">Retiros para la casa</div><div className="v">{soles(p.withdrawals_cents)}</div></div>
            </div>
            <div style={{ marginTop: 18 }}>
              <div className="eyebrow">Cómo te pagaron {periodLabel}</div>
              <Stacked parts={[
                { label: 'Efectivo', value: p.sales_by_method.efectivo, color: 'var(--cash)' },
                { label: 'Yape', value: p.sales_by_method.yape, color: 'var(--yape)' },
                { label: 'Fiado', value: p.sales_by_method.fiado, color: 'var(--sand)' },
              ]} />
            </div>
          </div>

          <div className="card">
            <div className="card-head"><h2>Flujo de caja · 30 días</h2><span className="pill">entró vs salió</span></div>
            <FlowChart rows={d.series} height={200} />
          </div>

          <div className="grid-cards two">
            <div className="card">
              <div className="eyebrow">Tendencia</div>
              <div className="mid" style={{ color: d.trend.direction === 'peor' ? 'var(--bad)' : d.trend.direction === 'mejor' ? 'var(--good)' : undefined }}>
                {d.trend.pct === null ? '—' : `${d.trend.pct > 0 ? '+' : ''}${d.trend.pct}%`}</div>
              <div className="faint">vs. los mismos {d.trend.days_compared} días del mes pasado</div>
            </div>
            <div className="card">
              <div className="eyebrow">Punto de equilibrio</div>
              {d.break_even.available ? (
                <>
                  <div className="mid num">{soles(d.break_even.break_even_monthly_cents ?? 0)}</div>
                  <div className="faint">al mes para cubrir {soles(d.break_even.fixed_cents)} de gastos fijos</div>
                  <div style={{ margin: '10px 0 4px' }}><Progress pct={d.break_even.coverage_pct ?? 0} /></div>
                  <div className="faint">Cubres {d.break_even.coverage_pct}%</div>
                </>
              ) : <div className="faint">{d.break_even.reason}</div>}
            </div>
            <div className="card">
              <div className="eyebrow">Margen promedio</div>
              <div className="mid">{marginPct === null ? '—' : `${marginPct}%`}</div>
              <div className="faint">de cada S/ 100 vendidos te quedan S/ {marginPct ?? '—'} antes de gastos</div>
            </div>
            <div className="card">
              <div className="eyebrow">Rotación</div>
              <div className="kv"><span>Inventario</span><span>{d.rotation.inventory_days ?? '—'} días</span></div>
              <div className="kv"><span>Caja alcanza</span><span>{d.rotation.cash_days ?? '—'} días</span></div>
              <div className="kv"><span>Caja rota</span><span>{d.rotation.cash_turnover ?? '—'} /mes</span></div>
              <div className="kv"><span>Cobro fiados</span><span>{d.rotation.receivable_days ?? '—'} días</span></div>
            </div>
          </div>

          {d.margins.length > 0 && (
            <div className="card">
              <div className="card-head"><h2>Qué te deja más plata</h2><span className="pill">30 días</span></div>
              <HBars items={d.margins.map((m) => ({ name: m.name, value: m.margin_cents, note: 'falta costo' }))} />
              <p className="faint" style={{ margin: '10px 0 0' }}>Ganancia por producto (venta − costo). Por unidad: {d.margins.filter((m) => m.margin_per_unit_cents !== null).map((m) => `${m.name} ${soles(m.margin_per_unit_cents)}`).join(' · ')}</p>
            </div>
          )}

          {d.weekday.available && (
            <div className="card">
              <div className="card-head"><h2>Tus mejores días</h2><span className="pill">promedio 8 semanas</span></div>
              <Columns items={d.weekday.days.map((x) => ({ label: x.name.slice(0, 3), value: x.avg_sales_cents, title: `${x.name}: ${soles(x.avg_sales_cents)} (${x.vs_avg_pct > 0 ? '+' : ''}${x.vs_avg_pct}%)` }))}
                highlight={d.weekday.days.findIndex((x) => x.name === d.weekday.best?.name)} height={170} />
            </div>
          )}
        </div>

        <div>
          <div className="only-desktop">{cashCard}</div>
          <div className="only-desktop">{restockCard}</div>

          <div className="card">
            <div className="row" style={{ gap: 12, marginBottom: 6 }}>
              <span className="icon-box" style={{ width: 40, height: 40, borderRadius: 12, background: 'var(--sage)', color: 'var(--brand)', display: 'grid', placeItems: 'center' }}><IconSpark width={20} /></span>
              <h2 style={{ margin: 0 }}>Consejos con tus números</h2>
            </div>
            {d.advice.map((t, i) => <div key={i} className="tip"><span className="n">{i + 1}</span><span>{t}</span></div>)}
          </div>

          {ahorro.length > 0 && (
            <div className="card">
              <div className="card-head"><h2>Tus metas</h2><button className="linkbtn" onClick={() => ctx.go('metas')}>Ver metas <IconArrow /></button></div>
              {ahorro.map((g) => (
                <div key={g.id} style={{ marginBottom: 14 }}>
                  <div className="spread" style={{ marginBottom: 8 }}><b>{g.name}</b><span className={`pill ${g.behind ? 'warn' : 'good'}`}>{g.progress_pct}%{g.behind ? ' · atrasada' : ''}</span></div>
                  <Progress pct={g.progress_pct} accent={g.behind} />
                </div>
              ))}
            </div>
          )}

          <div className="card">
            <div className="card-head"><h2>Casa y negocio</h2><span className="pill">este mes</span></div>
            <Stacked parts={[
              { label: 'Compras', value: d.month.purchases_cents, color: 'var(--brand)' },
              { label: 'Gastos negocio', value: d.month.expenses_cents, color: 'var(--sage-3)' },
              { label: 'Casa', value: d.month.withdrawals_cents, color: 'var(--sand)' },
              { label: 'Metas', value: d.month.goal_savings_cents, color: 'var(--yape)' },
            ]} />
            {d.month.contributions_cents > 0 && <p className="faint" style={{ margin: '10px 0 0' }}>Pusiste {soles(d.month.contributions_cents)} de tu plata (no cuenta como venta).</p>}
          </div>

          {d.receivables.length > 0 && (
            <div className="card">
              <div className="card-head"><h2>Fiados por cobrar</h2><span className="mid num" style={{ fontSize: '1.1rem' }}>{soles(cash.receivables_cents)}</span></div>
              {d.receivables.map((r) => <div className="kv" key={r.sale_id}><span>{r.counterparty} · {fmtDate(r.occurred_at)}{r.product ? ` · ${r.product}` : ''}</span><span>{soles(r.pending_cents)}</span></div>)}
            </div>
          )}

          {d.inventory_flags.length > 0 && (
            <div className="card">
              <div className="card-head"><h2>Revisa tu mercadería</h2><button className="linkbtn" onClick={() => ctx.go('stock')}>Ir <IconArrow /></button></div>
              {d.inventory_flags.slice(0, 4).map((i) => (
                <div className="kv" key={i.id}><span>{i.name}</span><span className="small">{i.needs_restock ? `Quedan ${i.expected_stock}` : i.needs_review[0]}</span></div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
