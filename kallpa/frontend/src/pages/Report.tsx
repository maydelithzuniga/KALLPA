import { useEffect, useState } from 'react'
import type { Ctx } from '../App'
import { fmtDate, get, send, soles } from '../lib/api'
import { Columns } from '../components/charts'

type R = any // eslint-disable-line @typescript-eslint/no-explicit-any

const iso = (d: Date) => d.toISOString().slice(0, 10)
function range(kind: string): { start: string; end: string } {
  const now = new Date()
  const end = iso(now)
  if (kind === 'mes') return { start: iso(new Date(now.getFullYear(), now.getMonth(), 1)), end }
  if (kind === 'prev') {
    const s = new Date(now.getFullYear(), now.getMonth() - 1, 1), e = new Date(now.getFullYear(), now.getMonth(), 0)
    return { start: iso(s), end: iso(e) }
  }
  const months = kind === '6m' ? 5 : 2
  return { start: iso(new Date(now.getFullYear(), now.getMonth() - months, 1)), end }
}
const pct = (v: number | null | undefined) => (v === null || v === undefined ? '—' : `${v}%`)
const KIND: Record<string, string> = { venta: 'Venta', compra: 'Compra', gasto: 'Gasto', retiro_personal: 'Retiro casa', aporte: 'Aporte', traslado: 'Traslado', cobro_fiado: 'Cobro fiado', pago_deuda: 'Cuota', ajuste_stock: 'Ajuste stock', ahorro_meta: 'Ahorro meta' }

export default function Report({ ctx }: { ctx: Ctx }) {
  const bid = ctx.business.id
  const [period, setPeriod] = useState('3m')
  const [r, setR] = useState<R | null>(null)
  const [consent, setConsent] = useState<{ pending_month: string | null; pending_label: string | null; history: { month: string; decision: string; decided_at: string }[] } | null>(null)
  const [showAll, setShowAll] = useState(false)

  useEffect(() => {
    const { start, end } = range(period)
    setR(null)
    get<R>(`/api/businesses/${bid}/report?start=${start}&end=${end}`).then(setR).catch(() => setR({ error: true }))
  }, [bid, period, ctx.tick])
  useEffect(() => { get<typeof consent>(`/api/businesses/${bid}/report/consent`).then(setConsent).catch(() => undefined) }, [bid, ctx.tick])

  async function decide(month: string, decision: 'si' | 'no') {
    setConsent(await send(`/api/businesses/${bid}/report/consent`, { month, decision }))
    ctx.toast(decision === 'si' ? 'Autorizado. En esta demo el envío al BCP es simulado.' : 'No se enviará este mes.')
  }

  return (
    <div>
      <div className="no-print">
        <div className="card">
          <h2>Cada mes te pregunto</h2>
          {consent?.pending_month ? (
            <>
              <p style={{ marginTop: 0 }}>¿Quieres que tu informe de <b>{consent.pending_label}</b> se le envíe al BCP?</p>
              <div className="row"><button className="btn sm" onClick={() => decide(consent.pending_month!, 'si')}>Sí, envíalo</button>
                <button className="btn sm ghost" onClick={() => decide(consent.pending_month!, 'no')}>No por ahora</button></div>
            </>
          ) : <p className="faint" style={{ margin: 0 }}>No hay decisiones pendientes.</p>}
          {consent?.history.length ? <div style={{ marginTop: 8 }}>{consent.history.map((h) => <div className="kv" key={h.month}><span>{h.month}</span><span>{h.decision === 'si' ? 'Autorizado (envío simulado)' : 'No enviado'}</span></div>)}</div> : null}
          <p className="faint" style={{ marginBottom: 0 }}>Tú revisas el reporte y decides si lo descargas y lo presentas. Esta demo no se conecta con ningún banco.</p>
        </div>
        <div className="seg" style={{ marginBottom: 10 }}>
          {[['mes', 'Este mes'], ['prev', 'Mes pasado'], ['3m', '3 meses'], ['6m', '6 meses']].map(([k, l]) => <button key={k} className={period === k ? 'on' : ''} onClick={() => setPeriod(k)}>{l}</button>)}
        </div>
        <button className="btn block" style={{ marginBottom: 12 }} onClick={() => { setShowAll(true); setTimeout(() => window.print(), 150) }} disabled={!r || r.error}>Descargar PDF / Imprimir</button>
      </div>
      {!r && <div className="empty">Preparando tu reporte…</div>}
      {r?.error && <div className="banner bad">No pude generar el reporte sin conexión.</div>}
      {r && !r.error && <ReportDoc r={r} showAll={showAll} setShowAll={setShowAll} />}
    </div>
  )
}

function ReportDoc({ r, showAll, setShowAll }: { r: R; showAll: boolean; setShowAll: (v: boolean) => void }) {
  const s = r.summary, cap = r.capacity, st = r.stability, sen = r.seniority, dis = r.discipline, c = r.capital, dv = r.diversification, rel = r.reliability
  const detail = (r.movements as R[]).filter((m) => m.kind === 'venta' || m.kind === 'compra')
  const others = (r.movements as R[]).filter((m) => m.kind !== 'venta' && m.kind !== 'compra')
  const shown = showAll ? detail : detail.slice(-40)
  return (
    <article className="report">
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'flex-start' }}>
        <div>
          <h1>Reporte de ingresos y capacidad de pago</h1>
          <div><b>{r.business.name}</b>{r.business.owner_name ? ` · ${r.business.owner_name}` : ''} · {r.business.kind}</div>
          <div className="note">{r.business.description}</div>
        </div>
        <div className="note" style={{ textAlign: 'right' }}>Periodo<br /><b>{fmtDate(r.period.start)} – {fmtDate(r.period.end)}</b><br />Generado {fmtDate(r.generated_at, true)}</div>
      </div>
      {r.demo_data && <div className="demo-mark">DATOS DE DEMOSTRACIÓN — información ficticia para la presentación</div>}

      <h2>Resumen para la evaluación</h2>
      <div className="kpis">
        <div className="kpi"><b>{soles(s.sales_cents)}</b><span>Ventas del periodo</span></div>
        <div className="kpi"><b>{soles(cap.avg_net_cents)}</b><span>Flujo neto mensual promedio</span></div>
        <div className="kpi"><b>{soles(cap.suggested_max_installment_cents)}</b><span>Cuota máxima sugerida / mes</span></div>
        <div className="kpi"><b>{sen.consecutive_months} meses</b><span>Registro continuo</span></div>
        <div className="kpi"><b>{pct(sen.active_days_pct)}</b><span>Días con registros</span></div>
        <div className="kpi"><b>{st.label ?? '—'}</b><span>Estabilidad de ventas</span></div>
        <div className="kpi"><b>{pct(rel.sales_backed_pct)}</b><span>Ventas respaldadas por Yape</span></div>
        <div className="kpi"><b>{dv.distinct_yape_payers}</b><span>Pagadores Yape distintos</span></div>
      </div>

      <h2>1. Capacidad de pago</h2>
      <p className="note">Flujo neto = cobrado − compras − gastos del negocio − retiros para la casa − cuotas actuales.</p>
      <div className="scroll"><table>
        <thead><tr><th>Mes</th><th className="n">Ventas</th><th className="n">Cobrado</th><th className="n">Compras</th><th className="n">Gastos neg.</th><th className="n">Casa</th><th className="n">Cuotas</th><th className="n">Flujo neto</th></tr></thead>
        <tbody>{r.months.map((m: R) => (
          <tr key={m.month}><td>{m.label}{m.full_month ? '' : ' (parcial)'}</td><td className="n">{soles(m.sales_cents)}</td><td className="n">{soles(m.collected_cents)}</td>
            <td className="n">{soles(m.purchases_cents)}</td><td className="n">{soles(m.expenses_cents)}</td><td className="n">{soles(m.withdrawals_cents)}</td>
            <td className="n">{soles(m.debt_payments_cents)}</td><td className="n"><b>{soles(m.net_cents)}</b></td></tr>))}</tbody>
      </table></div>
      <table style={{ marginTop: 6 }}><tbody>
        <tr><td>Flujo neto mensual promedio ({cap.months_used} meses)</td><td className="n"><b>{soles(cap.avg_net_cents)}</b></td></tr>
        <tr><td>Peor mes</td><td className="n">{soles(cap.worst_net_cents)}</td></tr>
        <tr><td>Cuotas de deudas actuales (ya descontadas)</td><td className="n">{soles(cap.current_debt_installments_cents)}</td></tr>
        <tr><td>Cuota máxima sugerida · <span className="note">{cap.rule}</span></td><td className="n"><b>{soles(cap.suggested_max_installment_cents)}</b></td></tr>
      </tbody></table>

      <h2>2. Estabilidad de ingresos</h2>
      <Columns items={(st.weekly as R[]).map((w) => ({ label: fmtDate(w.week_start).replace('.', ''), value: w.sales_cents }))} height={110} />
      <table><tbody>
        <tr><td>Ventas por semana: mínima / máxima</td><td className="n">{soles(st.min_week_cents)} / {soles(st.max_week_cents)}</td></tr>
        <tr><td>Variación promedio semana a semana</td><td className="n">{pct(st.avg_week_change_pct)}</td></tr>
        <tr><td>Coeficiente de variación semanal</td><td className="n">{st.cv ?? '—'} · {st.label ?? ''}</td></tr>
        {st.weekday.available && <tr><td>Estacionalidad semanal</td><td className="n">Mejor: {st.weekday.best.name} ({st.weekday.best.vs_avg_pct > 0 ? '+' : ''}{st.weekday.best.vs_avg_pct}%) · Más bajo: {st.weekday.worst.name} ({st.weekday.worst.vs_avg_pct}%)</td></tr>}
      </tbody></table>

      <h2>3. Antigüedad y constancia</h2>
      <table><tbody>
        <tr><td>Primer registro</td><td className="n">{sen.first_record ? fmtDate(sen.first_record) : '—'}</td></tr>
        <tr><td>Meses con registros / continuos hasta hoy</td><td className="n">{sen.months_with_records} / {sen.consecutive_months}</td></tr>
        <tr><td>Días activos en el periodo</td><td className="n">{sen.active_days} de {sen.period_days} ({pct(sen.active_days_pct)})</td></tr>
        <tr><td>Promedio de días activos al mes</td><td className="n">{sen.avg_active_days_per_month ?? '—'}</td></tr>
      </tbody></table>

      <h2>4. Carácter y disciplina</h2>
      <table><tbody>
        <tr><td>Registra a diario</td><td className="n">{pct(dis.daily_record_pct)} de los días</td></tr>
        <tr><td>Separa casa y negocio</td><td className="n">{dis.separates_home_business ? `Sí · ${dis.withdrawals_registered} retiros registrados (${pct(dis.withdrawals_pct_of_sales)} de las ventas)` : 'Sin retiros registrados'}</td></tr>
        <tr><td>Paga a proveedores al comprar</td><td className="n">{pct(dis.suppliers_paid_on_purchase_pct)} de las compras</td></tr>
        <tr><td>Cuotas pagadas a tiempo</td><td className="n">{dis.debt_on_time_pct === null ? 'Sin deudas registradas' : `${dis.debt_on_time_pct}% (${dis.debt_payments.length} meses)`}</td></tr>
        <tr><td>Metas de ahorro al día</td><td className="n">{dis.savings_goals_total ? `${dis.savings_goals_on_track} de ${dis.savings_goals_total}` : 'Sin metas de ahorro'}</td></tr>
        {(dis.goals as R[]).map((g) => <tr key={g.name}><td className="note">Meta «{g.name}»</td><td className="n note">{g.progress_pct ?? '—'}%{g.behind ? ' · atrasada' : ''}</td></tr>)}
      </tbody></table>

      <h2>5. Capital del negocio</h2>
      <table><tbody>
        <tr><td>Inventario valorizado a costo</td><td className="n">{soles(c.inventory_value_cents)}</td></tr>
        {(c.inventory_items as R[]).map((i) => <tr key={i.name}><td className="note">· {i.name}: {i.units ?? 'sin dato'} u.</td><td className="n note">{soles(i.value_cents)}</td></tr>)}
        <tr><td>Equipos declarados</td><td className="n">{soles(c.assets_value_cents)}</td></tr>
        {(c.assets as R[]).map((a) => <tr key={a.name}><td className="note">· {a.name}</td><td className="n note">{soles(a.value_cents)}</td></tr>)}
        <tr><td>Caja promedio del periodo</td><td className="n">{c.avg_cash_cents === null ? 'Falta saldo inicial' : soles(c.avg_cash_cents)}</td></tr>
        <tr><td>Caja actual (efectivo + Yape)</td><td className="n">{c.cash_now.complete ? soles(c.cash_now.total_cents) : 'Información incompleta'}</td></tr>
      </tbody></table>

      <h2>6. Diversificación de clientes</h2>
      <table><tbody>
        <tr><td>Pagadores distintos en Yape</td><td className="n">{dv.distinct_yape_payers} ({dv.yape_payments} cobros)</td></tr>
        <tr><td>Peso del cliente principal en Yape</td><td className="n">{pct(dv.top_payer_share_pct)}</td></tr>
        <tr><td>Clientes con fiado</td><td className="n">{dv.distinct_credit_customers}</td></tr>
      </tbody></table>

      <h2>7. Confiabilidad del dato</h2>
      <table><tbody>
        <tr><td>Ventas respaldadas por cobro Yape vinculado</td><td className="n">{pct(rel.sales_backed_pct)} del monto ({soles(rel.backed_sales_cents)})</td></tr>
        <tr><td>Ventas por Yape con respaldo</td><td className="n">{pct(rel.yape_sales_backed_pct)}</td></tr>
        <tr><td>Compras con comprobante de proveedor</td><td className="n">{rel.purchases_with_receipt} de {rel.purchases_total}</td></tr>
        <tr><td>Movimientos por origen</td><td className="n">{Object.entries(rel.by_origin).map(([k, v]) => `${k}: ${v}`).join(' · ')}</td></tr>
      </tbody></table>
      <p className="note">Autodeclarado: dictado por la emprendedora. Respaldo Yape: vinculado a un cobro Yape. Con adjunto: tiene un archivo adjunto (se registra como tal, no verificado). Comprobante: compra respaldada por comprobante del proveedor.</p>

      <h2>8. Ventas, cobros y gastos del periodo</h2>
      <table><tbody>
        <tr><td>Ventas (precio final acordado)</td><td className="n">{soles(s.sales_cents)}</td></tr>
        <tr><td>Cobrado en efectivo / Yape</td><td className="n">{soles(s.collected_by_method.efectivo)} / {soles(s.collected_by_method.yape)}</td></tr>
        <tr><td>Cobros de fiados anteriores (incluidos arriba)</td><td className="n">{soles(s.collections_cents)}</td></tr>
        <tr><td>Descuentos aplicados</td><td className="n">{soles(s.discounts_cents)} en {s.discount_sales} ventas</td></tr>
        <tr><td>Compras de mercadería e insumos</td><td className="n">{soles(s.purchases_cents)}</td></tr>
        <tr><td>Gastos del negocio</td><td className="n">{soles(s.expenses_cents)}</td></tr>
        {Object.entries(s.expenses_by_category as Record<string, number>).map(([k, v]) => <tr key={k}><td className="note">· {k}</td><td className="n note">{soles(v)}</td></tr>)}
        <tr><td>Retiros personales (casa)</td><td className="n">{soles(s.withdrawals_cents)}</td></tr>
        <tr><td>Aportes propios (no son ventas)</td><td className="n">{soles(s.contributions_cents)}</td></tr>
        <tr><td>Pago de cuotas</td><td className="n">{soles(s.debt_payments_cents)}</td></tr>
        <tr><td>Traslados entre efectivo y Yape (no cambian ingresos)</td><td className="n">{soles(s.transfers_cents)}</td></tr>
        <tr><td><b>Ganancia estimada</b> (ventas − costo de lo vendido − gastos)</td><td className="n"><b>{soles(s.profit_cents)}</b></td></tr>
      </tbody></table>

      <h2>9. Cobros pendientes (fiados)</h2>
      {r.receivables.length ? <table><thead><tr><th>Cliente</th><th>Desde</th><th className="n">Pendiente</th></tr></thead>
        <tbody>{(r.receivables as R[]).map((x) => <tr key={x.sale_id}><td>{x.counterparty}</td><td>{fmtDate(x.occurred_at)}</td><td className="n">{soles(x.pending_cents)}</td></tr>)}</tbody></table>
        : <p className="note">Sin cobros pendientes.</p>}

      <h2>10. Margen por producto</h2>
      <table><thead><tr><th>Producto</th><th className="n">Unid.</th><th className="n">Ventas</th><th className="n">Margen</th><th className="n">%</th></tr></thead>
        <tbody>{(r.margins as R[]).map((m) => <tr key={m.product_id}><td>{m.name}</td><td className="n">{m.units}</td><td className="n">{soles(m.revenue_cents)}</td><td className="n">{m.margin_cents === null ? 'pendiente' : soles(m.margin_cents)}</td><td className="n">{pct(m.margin_pct)}</td></tr>)}</tbody></table>
      {r.break_even.available && <p className="note">Punto de equilibrio: {soles(r.break_even.break_even_monthly_cents)} de ventas al mes para cubrir {soles(r.break_even.fixed_cents)} de gastos fijos (margen de contribución {r.break_even.contribution_margin_pct}%).</p>}

      <h2>11. Observaciones de conciliación</h2>
      {r.reconciliation.observations.length ? <table><thead><tr><th>Fecha</th><th>Ítem</th><th className="n">Esperado</th><th className="n">Contado</th><th>Resultado</th></tr></thead>
        <tbody>{(r.reconciliation.observations as R[]).slice(-15).map((o, i) => <tr key={i}><td>{fmtDate(o.date)}</td><td>{o.item}</td>
          <td className="n">{o.expected === null ? '—' : o.kind === 'caja' ? soles(o.expected) : o.expected}</td><td className="n">{o.kind === 'caja' ? soles(o.counted) : o.counted}</td>
          <td><span className={`tag ${o.result === 'Consistente' ? 'ok' : o.result === 'Con diferencia' ? 'dif' : ''}`}>{o.result}</span>{o.review_status === 'pendiente' ? ' · pendiente de revisar' : o.review_status === 'ajustado' ? ' · ajustado' : ''}</td></tr>)}</tbody></table>
        : <p className="note">Sin conteos registrados en el periodo.</p>}
      <p className="note">Un conteo autodeclarado aporta coherencia interna: compara stock inicial + compras − ventas ± mermas con lo contado.</p>

      <h2>12. Detalle de ventas y compras</h2>
      <div className="scroll"><table>
        <thead><tr><th>Fecha</th><th>Tipo</th><th>Producto</th><th className="n">Precio habitual</th><th className="n">Desc.</th><th className="n">Cobrado/Pagado</th><th>Medio</th><th>Origen</th><th>Cruce</th></tr></thead>
        <tbody>{shown.map((m: R) => (
          <tr key={m.id}><td>{fmtDate(m.date)}</td><td>{KIND[m.kind]}{m.revision > 1 ? '*' : ''}</td><td>{m.quantity ? `${m.quantity} ` : ''}{m.product ?? m.category ?? ''}</td>
            <td className="n">{m.reference_total_cents !== null ? soles(m.reference_total_cents) : '—'}</td>
            <td className="n">{m.discount_cents === null ? '—' : soles(m.discount_cents)}</td>
            <td className="n">{soles(m.amount_cents)}{m.paid_cents !== m.amount_cents ? ` (${soles(m.paid_cents)})` : ''}</td>
            <td>{m.method ?? 'fiado'}</td>
            <td><span className={`tag ${m.origin === 'Respaldo Yape' ? 'yape' : m.origin === 'Comprobante de proveedor' ? 'ok' : ''}`}>{m.origin}</span></td>
            <td><span className={`tag ${m.check === 'Consistente' ? 'ok' : m.check === 'Con diferencia' ? 'dif' : ''}`}>{m.check}</span></td></tr>))}</tbody>
      </table></div>
      {!showAll && detail.length > shown.length && <button className="btn sm ghost no-print" onClick={() => setShowAll(true)}>Ver los {detail.length} movimientos</button>}
      <p className="note">* Movimiento corregido; el historial de cambios se conserva. {others.length} movimientos adicionales (gastos, retiros, aportes, traslados, cuotas) están resumidos en la sección 8.</p>

      <h2>Nota</h2>
      <p className="note">{r.disclaimer}</p>
    </article>
  )
}
