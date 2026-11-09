"""Informe financiero formal en PDF (para que el banco evalúe un producto financiero).

Usa SOLO ingresos y egresos por Yape verificados con el registro de Yape (report.build_bcp).
El perfil del negocio (rubro, gastos declarados) se muestra como contexto y se marca como «declarado».
"""
from __future__ import annotations

import hashlib
import io
import json
import statistics
from datetime import date, datetime
from typing import Any

from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (BaseDocTemplate, Frame, KeepTogether, PageBreak, PageTemplate, Paragraph, Spacer, Table,
                                TableStyle)
from sqlalchemy import func, select

from . import metrics
from . import models as M
from .report import build_bcp

NAVY = colors.HexColor("#0b2a35")
SAGE = colors.HexColor("#2f7a68")
SAGE_SOFT = colors.HexColor("#e8f2ee")
SAND = colors.HexColor("#d9ad6d")
SAND_SOFT = colors.HexColor("#faf3e4")
INK = colors.HexColor("#1d2b30")
MUTED = colors.HexColor("#5d6d72")
LINE = colors.HexColor("#d5e0dc")
GOOD = colors.HexColor("#2e8b57")
WARN = colors.HexColor("#c98a1b")
BAD = colors.HexColor("#c0392b")

TEA_REF = 0.40   # tasa efectiva anual referencial para la simulación (el banco aplica la suya)

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
         "noviembre", "diciembre"]
RUBRO = {"verduras": "Comercio minorista de verduras y frutas", "reventa": "Comercio minorista (compra y reventa)",
         "comida": "Venta de comida preparada", "servicios": "Servicios personales"}


def S(cents: int | float | None, dec: bool = True) -> str:
    if cents is None:
        return "—"
    v = cents / 100
    s = f"{abs(v):,.2f}" if dec else f"{abs(v):,.0f}"
    return ("-S/ " if v < 0 else "S/ ") + s


def fdate(d: date | str) -> str:
    if isinstance(d, str):
        d = date.fromisoformat(d[:10])
    return f"{d.day} de {MESES[d.month - 1]} de {d.year}"


# ------------------------------------------------------------------ estilos
def _styles() -> dict[str, ParagraphStyle]:
    base = dict(fontName="Helvetica", fontSize=9.2, leading=13, textColor=INK)
    return {
        "body": ParagraphStyle("body", **base),
        "small": ParagraphStyle("small", **{**base, "fontSize": 7.8, "leading": 10.5, "textColor": MUTED}),
        "h1": ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=17, leading=21, textColor=NAVY),
        "h2": ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=11.5, leading=15, textColor=SAGE, spaceBefore=10, spaceAfter=5),
        "h3": ParagraphStyle("h3", fontName="Helvetica-Bold", fontSize=9.5, leading=13, textColor=NAVY, spaceBefore=4, spaceAfter=2),
        "kpi_v": ParagraphStyle("kpi_v", fontName="Helvetica-Bold", fontSize=13, leading=16, textColor=NAVY),
        "kpi_l": ParagraphStyle("kpi_l", fontName="Helvetica", fontSize=7.6, leading=9.5, textColor=MUTED),
        "cell": ParagraphStyle("cell", **{**base, "fontSize": 8.4, "leading": 11}),
        "cell_r": ParagraphStyle("cell_r", **{**base, "fontSize": 8.4, "leading": 11, "alignment": TA_RIGHT}),
        "cell_b": ParagraphStyle("cell_b", **{**base, "fontName": "Helvetica-Bold", "fontSize": 8.4, "leading": 11}),
        "conclusion": ParagraphStyle("conclusion", **{**base, "fontSize": 9.6, "leading": 14}),
        "center": ParagraphStyle("center", **{**base, "alignment": TA_CENTER}),
    }


def _table(rows, widths, header=True, zebra=True, align_right_from: int | None = None, bold_last=False):
    t = Table(rows, colWidths=widths, repeatRows=1 if header else 0)
    st = [("FONT", (0, 0), (-1, -1), "Helvetica", 8.4), ("TEXTCOLOR", (0, 0), (-1, -1), INK),
          ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
          ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE)]
    if header:
        st += [("BACKGROUND", (0, 0), (-1, 0), NAVY), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
               ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8)]
    if zebra:
        for r in range(1 if header else 0, len(rows)):
            if r % 2 == 0:
                st.append(("BACKGROUND", (0, r), (-1, r), colors.HexColor("#f6f9f8")))
    if align_right_from is not None:
        st.append(("ALIGN", (align_right_from, 0), (-1, -1), "RIGHT"))
    if bold_last:
        st += [("FONT", (0, -1), (-1, -1), "Helvetica-Bold", 8.4), ("LINEABOVE", (0, -1), (-1, -1), 0.8, NAVY)]
    t.setStyle(TableStyle(st))
    return t


def _kpis(items, st, cols=4, width=180 * mm):
    cells = []
    for value, label in items:
        cells.append([Paragraph(value, st["kpi_v"]), Paragraph(label, st["kpi_l"])])
    rows = [cells[i:i + cols] for i in range(0, len(cells), cols)]
    for r in rows:
        while len(r) < cols:
            r.append("")
    t = Table(rows, colWidths=[width / cols] * cols)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), SAGE_SOFT), ("BOX", (0, 0), (-1, -1), 0.6, LINE),
                           ("INNERGRID", (0, 0), (-1, -1), 0.6, colors.white), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                           ("LEFTPADDING", (0, 0), (-1, -1), 8)]))
    return t


def _dot(level: str) -> str:
    c = {"verde": "#2e8b57", "ambar": "#c98a1b", "rojo": "#c0392b"}[level]
    word = {"verde": "Favorable", "ambar": "Aceptable", "rojo": "A mejorar"}[level]
    return f'<font color="{c}"><b>{word}</b></font>'


def _bar_chart(labels, series, names, width=180 * mm, height=55 * mm, palette=(SAGE, SAND)):
    d = Drawing(width, height)
    ch = VerticalBarChart()
    ch.x, ch.y, ch.width, ch.height = 34, 24, width - 50, height - 42
    ch.data = [[v / 100 for v in s] for s in series]
    ch.categoryAxis.categoryNames = labels
    ch.categoryAxis.labels.fontName = "Helvetica"
    ch.categoryAxis.labels.fontSize = 7
    ch.categoryAxis.labels.fillColor = MUTED
    ch.valueAxis.labels.fontName = "Helvetica"
    ch.valueAxis.labels.fontSize = 7
    ch.valueAxis.labels.fillColor = MUTED
    mx = max([max(s) for s in series if s] + [1]) / 100
    ch.valueAxis.valueMin = 0
    ch.valueAxis.valueMax = mx * 1.15
    ch.valueAxis.strokeColor = LINE
    ch.categoryAxis.strokeColor = LINE
    ch.valueAxis.gridStrokeColor = colors.HexColor("#eef3f1")
    ch.valueAxis.visibleGrid = True
    ch.barSpacing = 2
    ch.groupSpacing = 8
    for i, c in enumerate(palette[:len(series)]):
        ch.bars[i].fillColor = c
        ch.bars[i].strokeColor = None
    d.add(ch)
    x = 36
    for i, n in enumerate(names):
        d.add(String(x + 10, height - 10, n, fontName="Helvetica", fontSize=7.5, fillColor=MUTED))
        from reportlab.graphics.shapes import Rect
        d.add(Rect(x, height - 12, 7, 7, fillColor=palette[i], strokeColor=None))
        x += 10 + len(n) * 4.2 + 18
    return d


# ------------------------------------------------------------------ análisis
def analyze(db, b: M.Business, start: date | None = None, end: date | None = None) -> dict[str, Any]:
    r = build_bcp(db, b, start, end)
    cap, stab, cons, cli, disc, ver = r["capacity"], r["stability"], r["constancy"], r["clients"], r["discipline"], r["verification"]
    months = [m for m in r["months"] if m["operations"]]
    full = [m for m in months if m["full_month"]] or months
    by_type = {"compras": 0, "gastos": 0, "cuotas": 0, "personal": 0}
    for mv in r["movements"]:
        if mv["direction"] == "Egreso":
            t = mv["type"].lower()
            key = "compras" if "compra" in t else "cuotas" if "cuota" in t or "deuda" in t else "personal" if "casa" in t or "retiro" in t else "gastos"
            by_type[key] += mv["amount_cents"]
    tin, tout = r["totals"]["income_cents"], r["totals"]["out_cents"]
    avg_net = cap["avg_net_cents"] or 0
    inst = cap["current_installments_cents"] or 0
    dsr = round(100 * inst / avg_net) if avg_net > 0 else None
    growth = None
    if len(full) >= 2 and full[0]["income_cents"]:
        growth = round(100 * (full[-1]["income_cents"] / full[-1]["days"] - full[0]["income_cents"] / full[0]["days"])
                       / (full[0]["income_cents"] / full[0]["days"]))
    # simulación de crédito con la cuota máxima sugerida
    i_m = (1 + TEA_REF) ** (1 / 12) - 1
    cuota = max(0, (cap["suggested_max_installment_cents"] or 0) - inst)
    sim = [{"months": n, "amount_cents": int(round(cuota * (1 - (1 + i_m) ** -n) / i_m / 1000) * 1000) if cuota else 0,
            "installment_cents": cuota} for n in (6, 12, 18)]
    # semáforo
    def lvl(v, g, a, higher=True):
        if v is None:
            return "ambar"
        return ("verde" if v >= g else "ambar" if v >= a else "rojo") if higher else ("verde" if v <= g else "ambar" if v <= a else "rojo")
    neg_months = sum(1 for m in full if m["net_cents"] < 0)
    ind = [
        ("Antigüedad del registro verificado", f"{cons['consecutive_months']} meses seguidos", lvl(cons["consecutive_months"], 6, 3)),
        ("Constancia de operación", f"{cons['active_days']} de {cons['period_days']} días ({cons['active_days_pct']}%)", lvl(cons["active_days_pct"], 80, 60)),
        ("Estabilidad de ingresos semanales", f"{stab['label'] or '—'} (CV {stab['cv'] if stab['cv'] is not None else '—'})",
         lvl(stab["cv"], 0.2, 0.4, higher=False)),
        ("Flujo neto mensual", "Positivo todos los meses" if not neg_months else f"{neg_months} mes(es) negativo(s)",
         "verde" if not neg_months else "rojo"),
        ("Carga de deudas actual (cuotas / flujo neto)", f"{dsr}%" if dsr is not None else "Sin deudas registradas",
         "verde" if not inst else lvl(dsr, 30, 50, higher=False)),
        ("Diversificación de clientes", f"{cli['distinct_payers']} clientes · principal {cli['top_payer_share_pct'] or 0}%",
         lvl(cli["top_payer_share_pct"], 20, 40, higher=False)),
        ("Movimientos verificados con Yape", f"{ver['verified_pct'] or 0}% de lo registrado por Yape", lvl(ver["verified_pct"], 80, 60)),
        ("Separa gastos del hogar y del negocio", "Sí" if disc["separates_home_business"] else "No registrado",
         "verde" if disc["separates_home_business"] else "ambar"),
    ]
    greens = sum(1 for _, _, l in ind if l == "verde")
    reds = sum(1 for _, _, l in ind if l == "rojo")
    profile = ("Perfil favorable" if greens >= 6 and reds == 0 else "Perfil aceptable, con puntos a reforzar" if reds <= 1
               else "Perfil en construcción")
    # perfil declarado (contexto)
    fixed = metrics.declared_costs(db, b)
    first = db.scalar(select(func.min(M.Movement.occurred_at)).where(M.Movement.business_id == b.id))
    prods = db.scalars(select(M.Product.name).where(M.Product.business_id == b.id, M.Product.active.is_(True))).all()
    seed = json.dumps({"b": b.id, "p": r["period"], "t": r["totals"], "m": [(m["month"], m["income_cents"], m["out_cents"]) for m in r["months"]]},
                      sort_keys=True)
    code = f"KAL-{b.id:04d}-{r['period']['end'][:7].replace('-', '')}-{hashlib.sha256(seed.encode()).hexdigest()[:6].upper()}"
    avail = max(0, (cap["suggested_max_installment_cents"] or 0) - inst)
    return {**r, "available_installment_cents": avail, "full_months": full, "egress_by_type": by_type, "dsr_pct": dsr, "growth_pct": growth, "simulation": sim,
            "indicators": ind, "profile": profile, "greens": greens, "reds": reds, "code": code,
            "declared": {"fixed_month_cents": fixed["fijo"], "variable_month_cents": fixed["variable"],
                         "since": first.date().isoformat() if first else None, "products": prods,
                         "phone": b.phone, "methods": b.payment_methods or ["efectivo", "yape"]},
            "ratios": {"out_over_in_pct": round(100 * tout / tin) if tin else None,
                       "net_margin_pct": round(100 * (tin - tout) / tin) if tin else None}}


def conclusion(a: dict[str, Any]) -> str:
    cap, b = a["capacity"], a["business"]
    who = b.get("owner_name") or "La titular"
    sim12 = next((s for s in a["simulation"] if s["months"] == 12), None)
    txt = (f"{who} registra ingresos por Yape verificados por un promedio de <b>{S(cap['avg_income_cents'])} al mes</b> y un "
           f"flujo neto mensual promedio de <b>{S(cap['avg_net_cents'])}</b> (después de compras, gastos, cuotas y retiros "
           f"personales pagados por Yape). ")
    if a["growth_pct"] is not None:
        txt += (f"Sus ingresos {'crecieron' if a['growth_pct'] >= 0 else 'bajaron'} {abs(a['growth_pct'])}% entre el primer y el "
                f"último mes completo del periodo. ")
    txt += (f"Opera {a['constancy']['active_days_pct']}% de los días y cobra a {a['clients']['distinct_payers']} clientes distintos, "
            f"sin depender de uno solo. ")
    if a["available_installment_cents"]:
        txt += (f"Con criterios prudentes{' y descontando las cuotas que ya paga' if cap['current_installments_cents'] else ''} "
                f"podría asumir una <b>nueva cuota de hasta {S(a['available_installment_cents'])} al mes</b>")
        if sim12 and sim12["amount_cents"]:
            txt += f", equivalente a un crédito referencial de <b>{S(sim12['amount_cents'], dec=False)} a 12 meses</b>"
        txt += ". "
    txt += f"Resultado de la evaluación de indicadores: <b>{a['profile'].lower()}</b> ({a['greens']} de {len(a['indicators'])} favorables)."
    return txt


def products(a: dict[str, Any]) -> list[tuple[str, str, str]]:
    sim = {s["months"]: s for s in a["simulation"]}
    out = []
    if sim[12]["amount_cents"]:
        out.append(("Crédito para capital de trabajo",
                    f"Hasta {S(sim[6]['amount_cents'], False)} a 6 meses o {S(sim[12]['amount_cents'], False)} a 12 meses",
                    "Para comprar mercadería por volumen (jaba, saco, docena) a mejor precio. Su flujo diario por Yape permite "
                    "cuotas mensuales o semanales."))
    if a["constancy"]["consecutive_months"] >= 3 and sim[18]["amount_cents"]:
        out.append(("Crédito para equipamiento del puesto",
                    f"Hasta {S(sim[18]['amount_cents'], False)} a 18 meses",
                    "Balanza, congeladora, exhibidores o mejoras del puesto, que aumentan la capacidad de venta."))
    out.append(("Cuenta de ahorro vinculada a Yape",
                "Sin monto mínimo", "Para separar la plata del negocio y cumplir sus metas de ahorro (reposición, gastos fijos, colchón)."))
    if a["stability"]["cv"] is not None and a["stability"]["cv"] >= 0.2:
        out.append(("Línea revolvente o cuotas flexibles", "Según evaluación",
                    "Sus ingresos semanales varían: cuotas que se ajusten a temporadas reducen el riesgo de atraso."))
    return out


# ------------------------------------------------------------------ PDF
def build_pdf(db, b: M.Business, start: date | None = None, end: date | None = None) -> bytes:
    a = analyze(db, b, start, end)
    st = _styles()
    buf = io.BytesIO()
    W, H = A4
    gen = datetime.fromisoformat(a["generated_at"])

    def on_page(c, doc):
        c.saveState()
        c.setFillColor(NAVY)
        c.rect(0, H - 14 * mm, W, 14 * mm, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(15 * mm, H - 9 * mm, "KALLPA")
        c.setFont("Helvetica", 8.5)
        c.drawString(33 * mm, H - 9 * mm, "Informe financiero del negocio para evaluación de productos financieros")
        c.drawRightString(W - 15 * mm, H - 9 * mm, a["code"])
        c.setFillColor(MUTED)
        c.setFont("Helvetica", 7.2)
        c.drawString(15 * mm, 10 * mm, f"Confidencial · Generado el {fdate(gen.date())}, {gen:%H:%M} (hora de Lima) · "
                                       "Fuente: movimientos por Yape verificados con el registro de Yape")
        c.drawRightString(W - 15 * mm, 10 * mm, f"Página {doc.page}")
        c.setStrokeColor(LINE)
        c.line(15 * mm, 14 * mm, W - 15 * mm, 14 * mm)
        if a["demo_data"]:
            c.setFillColor(SAND_SOFT)
            c.rect(15 * mm, H - 21 * mm, W - 30 * mm, 5.5 * mm, stroke=0, fill=1)
            c.setFillColor(colors.HexColor("#8a5a00"))
            c.setFont("Helvetica-Bold", 7.5)
            c.drawCentredString(W / 2, H - 19.3 * mm, "DATOS DE DEMOSTRACIÓN — información ficticia para la presentación")
        c.restoreState()

    doc = BaseDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=24 * mm, bottomMargin=20 * mm,
                          title=f"Informe financiero — {a['business']['name']}", author="Kallpa", subject=a["code"])
    doc.addPageTemplates([PageTemplate(id="p", frames=[Frame(15 * mm, 18 * mm, W - 30 * mm, H - 42 * mm, id="f")], onPage=on_page)])
    E: list[Any] = []
    cap, bz, per = a["capacity"], a["business"], a["period"]

    # ---------------- portada / resumen ejecutivo
    E.append(Paragraph("Informe financiero del negocio", st["h1"]))
    E.append(Paragraph(f"Para evaluación de productos financieros · Periodo del {fdate(per['start'])} al {fdate(per['end'])}", st["small"]))
    E.append(Spacer(1, 8))
    dec = a["declared"]
    info = [
        ["Negocio", bz["name"], "Código de informe", a["code"]],
        ["Titular", bz.get("owner_name") or "—", "Fecha de emisión", fdate(gen.date())],
        ["Actividad", RUBRO.get(bz.get("kind") or "", "Microempresa"), "Registra en Kallpa desde", fdate(dec["since"]) if dec["since"] else "—"],
        ["Celular (WhatsApp)", (dec["phone"][:-4].replace(dec["phone"][2:-4], "*" * len(dec["phone"][2:-4])) + dec["phone"][-4:]) if dec["phone"] else "—",
         "Medios de cobro", " y ".join("Yape" if m == "yape" else "efectivo" for m in dec["methods"])],
    ]
    t = Table([[Paragraph(f"<font color='#5d6d72'>{r[0]}</font>", st["cell"]), Paragraph(f"<b>{r[1]}</b>", st["cell"]),
                Paragraph(f"<font color='#5d6d72'>{r[2]}</font>", st["cell"]), Paragraph(f"<b>{r[3]}</b>", st["cell"])] for r in info],
              colWidths=[30 * mm, 60 * mm, 38 * mm, 52 * mm])
    t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE), ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    E.append(t)
    E.append(Spacer(1, 8))
    E.append(Paragraph("Resumen ejecutivo", st["h2"]))
    box = Table([[Paragraph(conclusion(a), st["conclusion"])]], colWidths=[180 * mm])
    box.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), SAND_SOFT), ("LINEBEFORE", (0, 0), (0, -1), 3, SAND),
                             ("LEFTPADDING", (0, 0), (-1, -1), 10), ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    E.append(box)
    E.append(Spacer(1, 8))
    sim12 = next(s for s in a["simulation"] if s["months"] == 12)
    E.append(_kpis([
        (S(cap["avg_income_cents"]), "Ingreso mensual promedio<br/>(Yape verificado)"),
        (S(cap["avg_net_cents"]), "Flujo neto mensual promedio"),
        (S(a["available_installment_cents"]), "Cuota disponible para<br/>un nuevo crédito"),
        (S(sim12["amount_cents"], False), "Crédito referencial<br/>a 12 meses"),
        (f"{a['ratios']['net_margin_pct'] if a['ratios']['net_margin_pct'] is not None else '—'}%", "Margen de flujo neto<br/>(neto / ingresos)"),
        (f"{a['constancy']['active_days_pct']}%", "Días con operaciones<br/>verificadas"),
        (str(a["clients"]["distinct_payers"]), "Clientes distintos<br/>que pagaron por Yape"),
        (f"{a['dsr_pct']}%" if a["dsr_pct"] is not None else "0%", "Cuotas actuales /<br/>flujo neto"),
    ], st))
    E.append(Spacer(1, 8))
    E.append(Paragraph("Indicadores de evaluación", st["h2"]))
    rows = [["Indicador", "Valor", "Evaluación"]]
    for n, v, l in a["indicators"]:
        rows.append([Paragraph(n, st["cell"]), Paragraph(v, st["cell"]), Paragraph(_dot(l), st["cell"])])
    ti = _table(rows, [72 * mm, 72 * mm, 36 * mm], zebra=False)
    tints = {"verde": colors.HexColor("#e3f3ea"), "ambar": colors.HexColor("#fbf0d9"), "rojo": colors.HexColor("#f8e1de")}
    bars = {"verde": GOOD, "ambar": WARN, "rojo": BAD}
    ti.setStyle(TableStyle([x for i, (_, _, l) in enumerate(a["indicators"], start=1)
                            for x in (("BACKGROUND", (2, i), (2, i), tints[l]), ("LINEBEFORE", (2, i), (2, i), 3, bars[l]))]))
    E.append(ti)
    E.append(Paragraph(f"Resultado: <b>{a['profile']}</b> · {a['greens']} favorables, {a['reds']} a mejorar. "
                       "Umbrales en la sección 6 (Metodología).", st["small"]))

    # ---------------- 1. flujo verificado
    E.append(PageBreak())
    E.append(Paragraph("1. Ingresos y egresos verificados por mes", st["h2"]))
    E.append(Paragraph("Solo movimientos cobrados o pagados por Yape y conciliados uno a uno con el registro de Yape "
                       "(fecha, monto y contraparte). El efectivo no se incluye.", st["small"]))
    E.append(Spacer(1, 4))
    rows = [["Mes", "Ingresos", "Compras y gastos", "Cuotas", "Retiros personales", "Flujo neto", "Operaciones"]]
    for m in a["months"]:
        rows.append([m["label"] + ("" if m["full_month"] else " (parcial)"), S(m["income_cents"]), S(m["business_out_cents"]),
                     S(m["debt_cents"]), S(m["personal_cents"]), S(m["net_cents"]), str(m["operations"])])
    tot = a["totals"]
    rows.append(["Total del periodo", S(tot["income_cents"]), S(sum(m["business_out_cents"] for m in a["months"])),
                 S(sum(m["debt_cents"] for m in a["months"])), S(sum(m["personal_cents"] for m in a["months"])),
                 S(tot["net_cents"]), str(tot["operations"])])
    E.append(_table(rows, [34 * mm, 25 * mm, 28 * mm, 20 * mm, 27 * mm, 26 * mm, 20 * mm], align_right_from=1, bold_last=True))
    E.append(Spacer(1, 8))
    E.append(_bar_chart([m["label"].split(" ")[0][:3].capitalize() + ("*" if not m["full_month"] else "") for m in a["months"]],
                        [[m["income_cents"] for m in a["months"]], [m["out_cents"] for m in a["months"]]],
                        ["Ingresos verificados (S/)", "Egresos verificados (S/)"]))
    E.append(Paragraph("* mes parcial.", st["small"]))
    eb = a["egress_by_type"]
    tout = sum(eb.values()) or 1
    E.append(Paragraph("Composición de los egresos verificados", st["h3"]))
    rows = [["Tipo de egreso", "Monto", "% del total"]]
    for k, label in (("compras", "Compra de mercadería"), ("gastos", "Gastos operativos (alquiler, luz, bolsas, transporte)"),
                     ("cuotas", "Cuotas de deudas"), ("personal", "Retiros para el hogar")):
        rows.append([label, S(eb[k]), f"{round(100 * eb[k] / tout)}%"])
    E.append(_table(rows, [110 * mm, 40 * mm, 30 * mm], align_right_from=1))

    # ---------------- 2. capacidad de pago
    E.append(Paragraph("2. Capacidad de pago", st["h2"]))
    rows = [["Concepto", "Monto"],
            ["Ingreso mensual promedio verificado", S(cap["avg_income_cents"])],
            [f"Flujo neto mensual promedio ({cap['months_used']} mes(es) usados)", S(cap["avg_net_cents"])],
            ["Flujo neto del peor mes", S(cap["worst_net_cents"])],
            ["Cuotas que ya paga actualmente", S(cap["current_installments_cents"])],
            ["Cuota máxima total (40% del flujo promedio, sin pasar el 70% del peor mes)", S(cap["suggested_max_installment_cents"])],
            ["Cuota disponible para un nuevo crédito (cuota máxima − cuotas actuales)", S(a["available_installment_cents"])]]
    E.append(_table(rows, [140 * mm, 40 * mm], align_right_from=1, bold_last=True))
    E.append(Spacer(1, 6))
    E.append(Paragraph("Simulación referencial de crédito con la cuota disponible", st["h3"]))
    rows = [["Plazo", "Cuota mensual", "Monto de crédito referencial"]]
    for s_ in a["simulation"]:
        rows.append([f"{s_['months']} meses", S(s_["installment_cents"]), S(s_["amount_cents"], False)])
    E.append(_table(rows, [50 * mm, 60 * mm, 70 * mm], align_right_from=1))
    E.append(Paragraph(f"Simulación con una TEA referencial de {int(TEA_REF * 100)}% y cuotas fijas. El banco aplica su propia tasa, "
                       "plazo y política de riesgo.", st["small"]))
    if dec["fixed_month_cents"]:
        E.append(Spacer(1, 4))
        E.append(Paragraph(f"<b>Contexto declarado (no verificado):</b> la titular declaró gastos fijos de {S(dec['fixed_month_cents'])} "
                           f"al mes y gastos variables de {S(dec['variable_month_cents'])} al mes. No se usan en el cálculo; "
                           "sirven para contrastar con los egresos verificados.", st["small"]))

    # ---------------- 3. estabilidad y comportamiento
    E.append(PageBreak())
    E.append(Paragraph("3. Estabilidad de ingresos", st["h2"]))
    wk = a["stability"]["weekly"]
    labels = []
    for w in wk:
        d = date.fromisoformat(w["week_start"])
        labels.append(f"{d.day}/{d.month}")
    E.append(_bar_chart(labels, [[w["income_cents"] for w in wk]], ["Ingresos verificados por semana (S/)"], palette=(SAGE,)))
    stab = a["stability"]
    rows = [["Indicador", "Valor"],
            ["Ingreso semanal mínimo / máximo", f"{S(stab['min_week_cents'])} / {S(stab['max_week_cents'])}"],
            ["Coeficiente de variación semanal", f"{stab['cv']} — {stab['label']}" if stab["cv"] is not None else "—"],
            ["Variación de ingresos entre meses completos", f"{a['growth_pct']:+d}%" if a["growth_pct"] is not None else "Se necesitan 2 meses completos"]]
    E.append(_table(rows, [110 * mm, 70 * mm], align_right_from=1))
    E.append(Paragraph("4. Comportamiento y constancia", st["h2"]))
    cons, cli, disc, ver = a["constancy"], a["clients"], a["discipline"], a["verification"]
    rows = [["Indicador", "Valor"],
            ["Días con movimientos verificados", f"{cons['active_days']} de {cons['period_days']} ({cons['active_days_pct']}%)"],
            ["Meses seguidos con movimientos verificados", str(cons["consecutive_months"])],
            ["Clientes distintos que pagaron por Yape", str(cli["distinct_payers"])],
            ["Peso del cliente principal en los ingresos", f"{cli['top_payer_share_pct'] or 0}%"],
            ["Cuotas de deudas pagadas por Yape (a tiempo / total)",
             f"{disc['debt_on_time']} / {disc['debt_payments']}" if disc["debt_payments"] else "Sin cuotas en el periodo"],
            ["Separa gastos del hogar y del negocio", "Sí, registra los retiros para la casa aparte" if disc["separates_home_business"] else "No registrado"],
            ["Movimientos por Yape verificados", f"{ver['verified']} ({ver['verified_pct'] or 0}%) · {ver['pending']} sin verificar, no incluidos"]]
    E.append(_table(rows, [110 * mm, 70 * mm], align_right_from=1))

    # ---------------- 5. productos sugeridos
    E.append(Paragraph("5. Productos financieros sugeridos", st["h2"]))
    rows = [["Producto", "Monto / condición referencial", "Por qué encaja con este negocio"]]
    for n, m, w in products(a):
        rows.append([Paragraph(f"<b>{n}</b>", st["cell"]), Paragraph(m, st["cell"]), Paragraph(w, st["cell"])])
    E.append(_table(rows, [48 * mm, 50 * mm, 82 * mm]))
    E.append(Paragraph("Sugerencias generadas a partir de los indicadores de este informe; la decisión y las condiciones "
                       "corresponden a la entidad financiera.", st["small"]))

    # ---------------- 6. metodología
    E.append(KeepTogether([
        Paragraph("6. Metodología, fuentes y autorización", st["h2"]),
        Paragraph("<b>Fuente de datos.</b> La titular registra sus ventas, compras y gastos conversando con Kallpa (WhatsApp o app). "
                  "Para este informe se toman solo los movimientos hechos por Yape que coinciden con su registro de Yape "
                  "(monto, fecha y contraparte). El efectivo y los movimientos por Yape sin verificar se excluyen.", st["body"]),
        Spacer(1, 3),
        Paragraph("<b>Cálculos.</b> Flujo neto = ingresos verificados − (compras + gastos + cuotas + retiros personales) verificados. "
                  "Los meses parciales se llevan a 30 días para el promedio. Cuota máxima = mín(40% del flujo neto promedio; "
                  "70% del flujo del peor mes) − cuotas vigentes. Coeficiente de variación = desviación estándar / promedio de "
                  "los ingresos semanales.", st["body"]),
        Spacer(1, 3),
        Paragraph("<b>Umbrales del semáforo.</b> Antigüedad: favorable ≥ 6 meses, aceptable ≥ 3. Constancia: ≥ 80% / ≥ 60% de días. "
                  "Estabilidad (CV): ≤ 0.20 / ≤ 0.40. Carga de deudas: ≤ 30% / ≤ 50%. Cliente principal: ≤ 20% / ≤ 40%. "
                  "Verificación: ≥ 80% / ≥ 60%.", st["body"]),
        Spacer(1, 3),
        Paragraph("<b>Autorización.</b> " + (
            f"La titular autorizó el envío de su informe del mes {a['consents'][0]['month']} el "
            f"{fdate(a['consents'][0]['decided_at'])}." if a["consents"] and a["consents"][0]["decision"] == "si"
            else "El envío de este informe requiere la autorización de la titular, que se solicita cada mes."), st["body"]),
        Spacer(1, 3),
        Paragraph(f"<b>Verificación.</b> Código {a['code']}: identifica este informe y sus totales. "
                  + a["disclaimer"], st["small"]),
    ]))

    # ---------------- declaración y firma
    E.append(Spacer(1, 10))
    firma = Table([[Paragraph("<b>Declaración de la titular</b><br/>Declaro que la información de mi negocio registrada en Kallpa es "
                              "verdadera y autorizo que este informe sea compartido con la entidad financiera para evaluar "
                              "productos financieros a mi favor.", st["small"]),
                    Paragraph("<br/><br/>_______________________________<br/>"
                              f"{bz.get('owner_name') or 'Titular'} · Firma o aceptación digital por WhatsApp", st["small"])]],
                  colWidths=[110 * mm, 70 * mm])
    firma.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.6, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("LEFTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    E.append(firma)

    # ---------------- anexos
    E.append(Spacer(1, 6))
    E.append(Paragraph("Anexo A. Mayores ingresos verificados del periodo", st["h2"]))
    mv = a["movements"]
    ins = sorted([m for m in mv if m["direction"] == "Ingreso"], key=lambda m: -m["amount_cents"])[:10]
    rows = [["Fecha", "Detalle", "Cliente", "Operación Yape", "Monto"]]
    for m in ins:
        rows.append([fdate(m["date"]).rsplit(" de ", 1)[0], Paragraph(m["description"] or "Venta", st["cell"]), m["counterpart"] or "—",
                     m["operation_code"] or "—", S(m["amount_cents"])])
    E.append(_table(rows, [30 * mm, 50 * mm, 35 * mm, 40 * mm, 25 * mm], align_right_from=4))
    E.append(Paragraph(f"Se muestran los 10 mayores de {a['totals']['income_operations']} ingresos verificados. "
                       "El detalle completo está disponible en formato CSV.", st["small"]))
    outs = [m for m in mv if m["direction"] == "Egreso"]
    E.append(Paragraph("Anexo B. Egresos verificados del periodo", st["h2"]))
    rows = [["Fecha", "Tipo", "Detalle", "Operación Yape", "Monto"]]
    for m in sorted(outs, key=lambda m: m["date"])[:30]:
        rows.append([fdate(m["date"]).rsplit(" de ", 1)[0], Paragraph(m["type"], st["cell"]), Paragraph(m["description"] or "—", st["cell"]),
                     m["operation_code"] or "—", S(m["amount_cents"])])
    E.append(_table(rows, [30 * mm, 38 * mm, 52 * mm, 35 * mm, 25 * mm], align_right_from=4))
    if len(outs) > 30:
        E.append(Paragraph(f"Se muestran 30 de {len(outs)} egresos; el detalle completo está en el CSV.", st["small"]))

    doc.build(E)
    return buf.getvalue()


def movements_csv(db, b: M.Business, start: date | None = None, end: date | None = None) -> str:
    r = build_bcp(db, b, start, end)
    lines = ["fecha,tipo,sentido,detalle,contraparte,operacion_yape,monto_soles"]
    for m in r["movements"]:
        def q(x):
            return '"' + str(x or "").replace('"', "'") + '"'
        lines.append(",".join([m["date"][:19], q(m["type"]), m["direction"], q(m["description"]), q(m["counterpart"]),
                               q(m["operation_code"]), f"{m['amount_cents'] / 100:.2f}"]))
    return "\n".join(lines) + "\n"
