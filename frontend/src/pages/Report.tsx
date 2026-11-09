import { useEffect, useState } from 'react'
import type { Ctx } from '../App'
import { fmtDate, get, send, soles } from '../lib/api'
import { Columns } from '../components/charts'
import { isBrowserDemo } from '../lib/browserBackend'

type R = any // eslint-disable-line @typescript-eslint/no-explicit-any

const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
function range(kind: string): { start: string; end: string } {
  const now = new Date()
  const end = iso(now)
  if (kind === 'mes') return { start: iso(new Date(now.getFullYear(), now.getMonth(), 1)), end }
  if (kind === 'prev') return { start: iso(new Date(now.getFullYear(), now.getMonth() - 1, 1)), end: iso(new Date(now.getFullYear(), now.getMonth(), 0)) }
  return { start: iso(new Date(now.getFullYear(), now.getMonth() - (kind === '6m' ? 5 : 2), 1)), end }
}
const pct = (v: number | null | undefined) => (v === null || v === undefined ? '—' : `${v}%`)

/** Informe para el BCP: solo ingresos y egresos por Yape verificados. */
export default function Report({ ctx }: { ctx: Ctx }) {
  const bid = ctx.business.id
  const [period, setPeriod] = useState('3m')
  const [r, setR] = useState<R | null>(null)
  const [consent, setConsent] = useState<{ pending_month: string | null; pending_label: string | null; history: { month: string; decision: string }[] } | null>(null)
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
        <div className="qcard" style={{ background: 'var(--brand-soft)', borderColor: 'var(--sage-2)' }}>
          <div className="qtitle">¿Qué va en este informe?</div>
          <p className="say" style={{ marginTop: 8 }}>
            Solo tus <b>ingresos y gastos por Yape que se verificaron</b> con tu registro de Yape. Lo que pagaste o cobraste
            en <b>efectivo no se incluye</b>. Para que un movimiento entre, al dictarlo di si fue «por Yape».
          </p>
        </div>
        {consent?.pending_month && (
          <div className="qcard">
            <div className="qtitle">¿Enviamos tu informe de {consent.pending_label} al BCP?</div>
            <div className="row" style={{ marginTop: 12 }}>
              <button className="btn sm" onClick={() => decide(consent.pending_month!, 'si')}>Sí, envíalo</button>
              <button className="btn sm ghost" onClick={() => decide(consent.pending_month!, 'no')}>No por ahora</button>
            </div>
            <p className="faint" style={{ marginBottom: 0 }}>Te lo pregunto cada mes. En esta demo el envío es simulado.</p>
          </div>
        )}
        <div className="seg" style={{ marginBottom: 14 }}>
          {[['mes', 'Este mes'], ['prev', 'Mes pasado'], ['3m', '3 meses'], ['6m', '6 meses']].map(([k, l]) =>
            <button key={k} className={period === k ? 'on' : ''} onClick={() => setPeriod(k)}>{l}</button>)}
        </div>
        {!isBrowserDemo() && (
          <button className="btn block" style={{ marginBottom: 14 }} disabled={!r || r.error}
            onClick={() => { setShowAll(true); setTimeout(() => window.print(), 150) }}>Descargar PDF</button>
        )}
        {r && !r.error && r.verification.pending > 0 && (
          <div className="banner warn">{r.verification.pending} movimientos por Yape aún no se verifican y no entran al informe. Puedes verlos en Historial.</div>
        )}
      </div>
      {!r && <div className="empty">Preparando tu informe…</div>}
      {r?.error && <div className="banner bad">No pude generar el informe sin conexión.</div>}
      {r && !r.error && <Doc r={r} showAll={showAll} setShowAll={setShowAll} />}
    </div>
  )
}

function Doc({ r, showAll, setShowAll }: { r: R; showAll: boolean; setShowAll: (v: boolean) => void }) {
  const t = r.totals, cap = r.capacity, st = r.stability, con = r.constancy, cl = r.clients, dis = r.discipline, ver = r.verification
  const rows: R[] = showAll ? r.movements : r.movements.slice(-30)
  return (
    <article className="report">
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'flex-start', flexWrap: 'wrap' }}>
        <div>
          <h1>Informe de ingresos y gastos por Yape</h1>
          <div><b>{r.business.name}</b>{r.business.owner_name ? ` · ${r.business.owner_name}` : ''}</div>
          <div className="note">{r.business.description}</div>
        </div>
        <div className="note" style={{ textAlign: 'right' }}>Periodo<br /><b>{fmtDate(r.period.start)} – {fmtDate(r.period.end)}</b><br />Generado {fmtDate(r.generated_at, true)}</div>
      </div>
      {r.demo_data && <div className="demo-mark">DATOS DE DEMOSTRACIÓN — información ficticia para la presentación</div>}
      <p className="note" style={{ marginTop: 8 }}><b>Criterio:</b> {r.rule}</p>

      <h2>Resumen</h2>
      <div className="kpis">
        <div className="kpi"><b>{soles(t.income_cents)}</b><span>Ingresos por Yape verificados</span></div>
        <div className="kpi"><b>{soles(t.out_cents)}</b><span>Egresos por Yape verificados</span></div>
        <div className="kpi"><b>{soles(cap.avg_net_cents)}</b><span>Saldo neto mensual promedio</span></div>
        <div className="kpi"><b>{soles(cap.suggested_max_installment_cents)}</b><span>Cuota máxima sugerida al mes</span></div>
      </div>

      <h2>1. Ingresos y egresos por mes</h2>
      <div className="scroll"><table>
        <thead><tr><th>Mes</th><th className="n">Ingresos</th><th className="n">Compras y gastos</th><th className="n">Cuotas</th><th className="n">Personales</th><th className="n">Saldo neto</th></tr></thead>
        <tbody>{r.months.map((m: R) => (
          <tr key={m.month}><td>{m.label}{m.full_month ? '' : ' (parcial)'}</td><td className="n">{soles(m.income_cents)}</td>
            <td className="n">{soles(m.business_out_cents)}</td><td className="n">{soles(m.debt_cents)}</td><td className="n">{soles(m.personal_cents)}</td>
            <td className="n"><b>{soles(m.net_cents)}</b></td></tr>))}</tbody>
      </table></div>

      <h2>2. Capacidad de pago</h2>
      <table><tbody>
        <tr><td>Ingreso mensual promedio por Yape ({cap.months_used} meses)</td><td className="n">{soles(cap.avg_income_cents)}</td></tr>
        <tr><td>Saldo neto mensual promedio (ingresos − egresos)</td><td className="n"><b>{soles(cap.avg_net_cents)}</b></td></tr>
        <tr><td>Peor mes</td><td className="n">{soles(cap.worst_net_cents)}</td></tr>
        <tr><td>Cuotas actuales que ya paga</td><td className="n">{soles(cap.current_installments_cents)}</td></tr>
        <tr><td>Cuota máxima sugerida · <span className="note">{cap.rule}</span></td><td className="n"><b>{soles(cap.suggested_max_installment_cents)}</b></td></tr>
      </tbody></table>

      <h2>3. Estabilidad de ingresos</h2>
      <Columns items={(st.weekly as R[]).map((w) => ({ label: fmtDate(w.week_start).replace('.', ''), value: w.income_cents }))} height={120} />
      <table><tbody>
        <tr><td>Ingresos por semana: mínimo / máximo</td><td className="n">{soles(st.min_week_cents)} / {soles(st.max_week_cents)}</td></tr>
        <tr><td>Resultado</td><td className="n">{st.label ?? '—'}{st.cv !== null ? ` (variación ${st.cv})` : ''}</td></tr>
      </tbody></table>

      <h2>4. Constancia y clientes</h2>
      <table><tbody>
        <tr><td>Días con movimientos verificados</td><td className="n">{con.active_days} de {con.period_days} ({pct(con.active_days_pct)})</td></tr>
        <tr><td>Meses seguidos con movimientos verificados</td><td className="n">{con.consecutive_months}</td></tr>
        <tr><td>Clientes distintos que pagaron por Yape</td><td className="n">{cl.distinct_payers}</td></tr>
        <tr><td>Peso del cliente principal</td><td className="n">{pct(cl.top_payer_share_pct)}</td></tr>
        <tr><td>Cuotas pagadas por Yape (a tiempo)</td><td className="n">{dis.debt_payments ? `${dis.debt_on_time} de ${dis.debt_payments}` : 'Ninguna en el periodo'}</td></tr>
        <tr><td>Separa gastos de la casa del negocio</td><td className="n">{dis.separates_home_business ? 'Sí, los registra aparte' : 'Sin registros'}</td></tr>
        <tr><td>Movimientos por Yape verificados</td><td className="n">{ver.verified} ({pct(ver.verified_pct)}) · {ver.pending} sin verificar, no incluidos</td></tr>
      </tbody></table>

      <h2>5. Detalle de movimientos verificados</h2>
      <div className="scroll"><table>
        <thead><tr><th>Fecha</th><th>Tipo</th><th>Detalle</th><th>Quién</th><th>Operación Yape</th><th className="n">Ingreso</th><th className="n">Egreso</th></tr></thead>
        <tbody>{rows.map((m: R) => (
          <tr key={m.id}><td>{fmtDate(m.date)}</td><td>{m.type}</td><td>{m.description}</td><td>{m.counterpart}</td>
            <td><span className="tag yape">{m.operation_code}</span></td>
            <td className="n">{m.direction === 'Ingreso' ? soles(m.amount_cents) : ''}</td>
            <td className="n">{m.direction === 'Egreso' ? soles(m.amount_cents) : ''}</td></tr>))}</tbody>
        <tfoot><tr><th colSpan={5}>Total del periodo</th><th className="n">{soles(t.income_cents)}</th><th className="n">{soles(t.out_cents)}</th></tr></tfoot>
      </table></div>
      {!showAll && r.movements.length > rows.length && <button className="btn sm ghost no-print" style={{ marginTop: 8 }} onClick={() => setShowAll(true)}>Ver los {r.movements.length} movimientos</button>}

      <h2>Nota</h2>
      <p className="note">{r.disclaimer}</p>
    </article>
  )
}
