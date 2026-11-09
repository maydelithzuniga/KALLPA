import { useEffect, useState } from 'react'
import type { Ctx } from '../App'
import { get, soles } from '../lib/api'
import { load, save } from '../lib/store'
import type { Dashboard, Period } from '../lib/types'
import { Columns, FlowChart, HBars, Progress, Stacked } from '../components/charts'

/** «Mis números»: gráficos e indicadores financieros explicados en palabras simples. */
export default function Numbers({ ctx }: { ctx: Ctx }) {
  const bid = ctx.business.id
  const [d, setD] = useState<Dashboard | null>(() => load<Dashboard | null>(`kallpa.dash.${bid}`, null))
  const [period, setPeriod] = useState<'day' | 'week' | 'month'>('month')
  useEffect(() => {
    get<Dashboard>(`/api/businesses/${bid}/dashboard`).then((x) => { setD(x); save(`kallpa.dash.${bid}`, x) }).catch(() => undefined)
  }, [bid, ctx.tick])
  if (!d) return <div className="empty">Cargando…</div>

  const p: Period = d[period]
  const label = { day: 'hoy', week: 'esta semana', month: 'este mes' }[period]
  const be = d.break_even
  const withCost = d.margins.filter((m) => m.margin_per_unit_cents !== null)
  const best = withCost[0]
  const weekBest = d.weekday.best?.name, weekWorst = d.weekday.worst?.name

  return (
    <div className="wrap">
      <div className="hello">
        <h1>Mis números</h1>
        <p style={{ textTransform: 'none' }}>Lo importante de tu semana, en pocas palabras.</p>
      </div>

      <div className="qcard" style={{ background: 'var(--brand-soft)', borderColor: 'var(--sage-2)' }}>
        <div className="qtitle">📅 Tu semana</div>
        <p style={{ margin: '10px 0 0', fontSize: '1.05rem', lineHeight: 1.6, color: 'var(--ink)' }}>{d.week_text}</p>
        <div className="chips">
          <span className="chip2">Vendiste <b>{soles(d.week.sales_cents)}</b></span>
          <span className="chip2">Ganaste <b>{soles(d.week.profit_cents)}</b></span>
          {(d.week as unknown as { loss_cents: number }).loss_cents > 0 && <span className="chip2">Perdiste <b>{soles((d.week as unknown as { loss_cents: number }).loss_cents)}</b></span>}
        </div>
      </div>

      {d.receivables.length > 0 && (
        <div className="qcard">
          <div className="qtitle">🤝 A quién tienes que cobrar</div>
          <p className="explain">Total: {soles(d.cash.receivables_cents)}. Esta lista también te llega por WhatsApp al final del día, de la semana y del mes.</p>
          {d.receivables.map((r) => (
            <div className="stat-row" key={r.counterparty}>
              <span className="l"><b>{r.counterparty}</b><small>{r.days === 0 ? 'de hoy' : r.days === 1 ? 'de ayer' : `hace ${r.days} días`}</small></span>
              <span className="v">{soles(r.pending_cents)}</span>
            </div>
          ))}
        </div>
      )}

      <div className="qcard">
        <div className="qtitle">💡 Consejos con tus números</div>
        {d.advice.map((t, i) => <div key={i} className="tip"><span className="n">{i + 1}</span><span>{t}</span></div>)}
      </div>

      <details className="more-charts">
        <summary>Ver gráficos y números</summary>
      <div className="seg" style={{ marginBottom: 16 }}>
        {(['day', 'week', 'month'] as const).map((k) => (
          <button key={k} className={period === k ? 'on' : ''} onClick={() => setPeriod(k)}>{{ day: 'Hoy', week: 'Esta semana', month: 'Este mes' }[k]}</button>
        ))}
      </div>

      <div className="qcard">
        <div className="qtitle">¿Cómo me fue {label}?</div>
        <div className="stat-row"><span className="l"><b>Vendiste</b><small>Todo lo que vendiste, cobrado o fiado</small></span><span className="v">{soles(p.sales_cents)}</span></div>
        <div className="stat-row"><span className="l"><b>Ganaste</b><small>Ventas − lo que te costó la mercadería − gastos del negocio</small></span>
          <span className="v" style={{ color: p.profit_cents >= 0 ? 'var(--good)' : 'var(--bad)' }}>{soles(p.profit_cents)}</span></div>
        <div className="stat-row"><span className="l"><b>Flujo de caja</b><small>Lo que de verdad entró a tu caja menos lo que salió</small></span><span className="v">{soles(p.business_cashflow_cents)}</span></div>
        <div className="stat-row"><span className="l"><b>Sacaste para la casa</b><small>No es gasto del negocio, pero baja tu caja</small></span><span className="v">{soles(p.withdrawals_cents)}</span></div>
        {d.trend.pct !== null && period === 'month' && (
          <p className="say" style={{ marginTop: 10 }}>
            {d.trend.direction === 'mejor' ? `Vas ${d.trend.pct}% mejor que el mes pasado a esta fecha. ¡Bien!`
              : d.trend.direction === 'peor' ? `Vas ${Math.abs(d.trend.pct)}% abajo del mes pasado a esta fecha.` : 'Vas parecido al mes pasado.'}
          </p>
        )}
      </div>

      <div className="qcard">
        <div className="qtitle">¿Cómo te pagaron {label}?</div>
        <p className="explain">Efectivo y Yape ya están en tu caja. El fiado todavía te lo deben.</p>
        <Stacked parts={[
          { label: 'Efectivo', value: p.sales_by_method.efectivo, color: 'var(--cash)' },
          { label: 'Yape', value: p.sales_by_method.yape, color: 'var(--yape)' },
          { label: 'Fiado', value: p.sales_by_method.fiado, color: 'var(--sand)' },
        ]} />
      </div>

      <div className="qcard">
        <div className="qtitle">¿Entra más plata de la que sale?</div>
        <p className="explain">Flujo de caja de los últimos 30 días. Verde: lo que entró cada día. Arena: lo que salió. La línea muestra cuánto vas juntando.</p>
        <FlowChart rows={d.series} height={190} />
      </div>

      {d.margins.length > 0 && (
        <div className="qcard">
          <div className="qtitle">¿Qué producto te deja más plata?</div>
          <p className="explain">Ganancia de cada producto en 30 días (lo que vendiste menos lo que te costó).
            {best ? ` Cada ${best.name.toLowerCase()} te deja ${soles(best.margin_per_unit_cents)}.` : ''}</p>
          <HBars items={d.margins.map((m) => ({ name: m.name, value: m.margin_cents, note: 'falta el costo' }))} />
        </div>
      )}

      {d.weekday.available && (
        <div className="qcard">
          <div className="qtitle">¿Qué días vendes más?</div>
          <p className="explain">Venta promedio por día de la semana. {weekBest && weekWorst ? `Tu mejor día es el ${weekBest}; el más flojo, el ${weekWorst}.` : ''}</p>
          <Columns items={d.weekday.days.map((x) => ({ label: x.name.slice(0, 3), value: x.avg_sales_cents, title: `${x.name}: ${soles(x.avg_sales_cents)}` }))}
            highlight={d.weekday.days.findIndex((x) => x.name === weekBest)} height={160} />
        </div>
      )}

      <div className="qcard">
        <div className="qtitle">¿Cuánto tengo que vender para no perder?</div>
        {be.available ? (
          <>
            <p className="explain">Punto de equilibrio: lo mínimo para cubrir tus gastos fijos ({soles(be.fixed_cents)} al mes: alquiler, luz, etc.).</p>
            <div className="answer" style={{ fontSize: '1.8rem' }}>{soles(be.break_even_monthly_cents ?? 0)} <span className="faint" style={{ fontSize: '.95rem', fontWeight: 400 }}>al mes</span></div>
            <p className="say" style={{ margin: '4px 0 10px' }}>Unos {soles(be.break_even_daily_cents ?? 0)} al día. En los últimos 30 días vendiste {soles(be.last30_sales_cents ?? 0)}: {(be.coverage_pct ?? 0) >= 100 ? 'ya los cubres.' : 'aún no llegas.'}</p>
            <Progress pct={Math.min(100, be.coverage_pct ?? 0)} />
          </>
        ) : <p className="say">{be.reason}</p>}
      </div>

      <div className="qcard">
        <div className="qtitle">¿Qué tan rápido se mueve tu plata?</div>
        <p className="explain">Rotación de caja e inventario.</p>
        <div className="stat-row"><span className="l"><b>Tu mercadería se vende en</b><small>Días que tardas en vender lo que tienes</small></span><span className="v">{d.rotation.inventory_days ?? '—'} días</span></div>
        <div className="stat-row"><span className="l"><b>Tu caja te alcanza para</b><small>Días de gastos que cubres con la plata de hoy</small></span><span className="v">{d.rotation.cash_days ?? '—'} días</span></div>
        <div className="stat-row"><span className="l"><b>Tu caja da vueltas</b><small>Veces al mes que entra y sale tu plata</small></span><span className="v">{d.rotation.cash_turnover ?? '—'} veces</span></div>
        <div className="stat-row"><span className="l"><b>Cobras tus fiados en</b><small>Días promedio que te deben</small></span><span className="v">{d.rotation.receivable_days ?? '—'} días</span></div>
      </div>

      <div className="qcard">
        <div className="qtitle">¿A dónde se fue tu plata este mes?</div>
        <p className="explain">Separar casa y negocio te ayuda a llegar a tus metas.</p>
        <Stacked parts={[
          { label: 'Mercadería', value: d.month.purchases_cents, color: 'var(--brand)' },
          { label: 'Gastos negocio', value: d.month.expenses_cents, color: 'var(--sage-3)' },
          { label: 'Casa', value: d.month.withdrawals_cents, color: 'var(--sand)' },
          { label: 'Metas', value: d.month.goal_savings_cents, color: 'var(--yape)' },
        ]} />
      </div>

      </details>
    </div>
  )
}
