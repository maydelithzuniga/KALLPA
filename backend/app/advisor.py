"""Asesor financiero de Kallpa: consejos, planes para metas y orientación sobre préstamos con los números del negocio.

Todo es corto (para WhatsApp) y usa lo que la persona ya registró: ventas, costos, gastos fijos declarados,
fiados, pérdidas y, si hay, el informe verificado por Yape. No promete créditos: da montos referenciales.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select

from . import ledger, metrics
from . import models as M
from .money import soles

TEA_REF = 0.40          # tasa referencial para simular cuotas (el banco aplica la suya)
SHARE_PROFIT = 0.30     # parte prudente de la ganancia mensual para una cuota
BUSINESS_GOAL_RE = re.compile(r"\b(congeladora|refrigeradora|balanza|vitrina|exhibidor|mostrador|puesto|local|stand|carretilla|"
                              r"triciclo|moto|maquina|cocina|horno|licuadora|mercaderia|reponer|surtir|stock|equipo|toldo|"
                              r"mesa|estante|anaquel|campana|negocio|tienda|bodega|olla|freidora|congelador|conservadora)\b")


def _i_month() -> float:
    return (1 + TEA_REF) ** (1 / 12) - 1


def loan_for_installment(cuota_cents: int, months: int) -> int:
    i = _i_month()
    return int(round(cuota_cents * (1 - (1 + i) ** -months) / i / 1000) * 1000) if cuota_cents > 0 else 0


def installment_for_loan(amount_cents: int, months: int) -> int:
    i = _i_month()
    return round(amount_cents * i / (1 - (1 + i) ** -months))


def _days_with_data(db, b: M.Business, today: date) -> int:
    first = db.scalar(select(func.min(M.Movement.occurred_at)).where(M.Movement.business_id == b.id,
                                                                      M.Movement.kind != M.OPENING))
    return max(1, min(30, (today - first.date()).days + 1)) if first else 0


def capacity(db, b: M.Business, today: date) -> dict[str, Any]:
    """Cuánto podría pagar de cuota al mes. Prefiere el informe verificado por Yape; si no hay, estima con todo lo registrado."""
    out: dict[str, Any] = {"source": None, "monthly_profit_cents": None, "monthly_sales_cents": None, "installment_cents": 0}
    days = _days_with_data(db, b, today)
    if days:
        st = metrics.period_stats(db, b, today - timedelta(days=days - 1), today + timedelta(days=1))
        out["monthly_sales_cents"] = round(st["sales_cents"] * 30 / days)
        fixed = metrics.declared_costs(db, b)["fijo"]
        # ganancia mensual = ganancia registrada llevada a 30 días, descontando gastos fijos aún no registrados
        prof = round(st["profit_cents"] * 30 / days)
        paid_fixed = round(st.get("fixed_expenses_cents", 0) * 30 / days)
        prof -= max(0, fixed - paid_fixed)
        out["monthly_profit_cents"] = prof
        out["days"] = days
        out["installment_cents"] = max(0, round(prof * SHARE_PROFIT))
        out["source"] = "estimado"
    try:
        from .report_pdf import analyze
        a = analyze(db, b)
        if a["capacity"]["avg_net_cents"] and a["verification"]["verified"] >= 20:
            out.update(source="yape", installment_cents=a["available_installment_cents"],
                       verified_income_cents=a["capacity"]["avg_income_cents"], profile=a["profile"])
    except Exception:   # noqa: BLE001 (sin movimientos por Yape aún)
        pass
    debts = db.scalars(select(M.Debt).where(M.Debt.business_id == b.id, M.Debt.active.is_(True))).all()
    out["current_installments_cents"] = sum(d.installment_cents for d in debts)
    if out["source"] == "estimado":
        out["installment_cents"] = max(0, out["installment_cents"] - out["current_installments_cents"])
    return out


# ------------------------------------------------------------------ consejos
def _product_margins(db, b: M.Business) -> list[tuple[str, int, int]]:
    out = []
    for p in db.scalars(select(M.Product).where(M.Product.business_id == b.id, M.Product.active.is_(True))).all():
        if p.price_cents and p.cost_cents and p.price_cents > 0:
            out.append((p.name, round(100 * (p.price_cents - p.cost_cents) / p.price_cents), p.price_cents - p.cost_cents))
    return sorted(out, key=lambda x: -x[1])


def advice_text(db, b: M.Business, today: date) -> str:
    tips: list[str] = []
    # 1) lo que ya calcula Kallpa con historia (comprar por volumen, días flojos, costos que suben…)
    for t in metrics.advice(db, b):
        if not t.startswith("Sigue mandando") and len(tips) < 2:
            tips.append(t)
    # 2) qué producto deja más
    mg = _product_margins(db, b)
    if len(mg) >= 2 and mg[0][1] - mg[-1][1] >= 10 and not any("te deja" in t for t in tips):
        tips.append(f"Tu {mg[0][0].lower()} te deja {mg[0][1]}% y {mg[-1][0].lower()} solo {mg[-1][1]}%: ofrece primero lo que "
                    f"más te deja y revisa si puedes subir un poco el precio de {mg[-1][0].lower()}.")
    # 3) gastos fijos: cuánto vender al día para cubrirlos (con el margen de sus productos)
    fixed = metrics.declared_costs(db, b)["fijo"]
    cap = capacity(db, b, today)
    if fixed and mg:
        avg_m = sum(m[1] for m in mg) / len(mg) / 100
        need = round(fixed / 30 / max(avg_m, 0.05))
        line = (f"Tus gastos fijos son {soles(fixed)} al mes ({soles(round(fixed / 30))} al día). Con tus márgenes necesitas "
                f"vender unos {soles(need)} al día para cubrirlos")
        if cap.get("days", 0) >= 7 and cap["monthly_sales_cents"] is not None:
            sell = round(cap["monthly_sales_cents"] / 30)
            line += f"; hoy vendes {soles(sell)} al día" + (" 👍." if sell >= need else ". Sube ventas o baja algún gasto fijo.")
        else:
            line += "."
        tips.append(line)
    # 4) fiados y pérdidas
    rec = sum(r["pending_cents"] for r in ledger.receivables(db, b.id))
    if rec and not any("fiado" in t.lower() for t in tips):
        tips.append(f"Te deben {soles(rec)} de fiados: cóbralos antes de fiar más; es plata tuya que no está trabajando.")
    st30 = metrics.period_stats(db, b, today - timedelta(days=29), today + timedelta(days=1))
    if st30.get("loss_cents"):
        tips.append(f"Perdiste {soles(st30['loss_cents'])} en mercadería malograda este mes: compra un poco menos de lo que "
                    "más se malogra y véndelo primero.")
    # 5) separar plata
    if cap["monthly_profit_cents"] and cap["monthly_profit_cents"] > 0:
        diario = round(cap["monthly_profit_cents"] * 0.2 / 30 / 100) * 100 or 100
        tips.append(f"Separa {soles(diario)} cada día al cerrar (el 20% de lo que ganas): en un mes son {soles(diario * 30)}.")
    if not tips:
        tips.append("Registra cada venta y gasto unos días más: con eso te digo qué producto te deja más y cuánto puedes ahorrar.")
    txt = "💡 Mis consejos para tu negocio:\n" + "\n".join(f"{i + 1}. {t}" for i, t in enumerate(tips[:4]))
    prod = product_line(db, b, today, cap)
    if prod:
        txt += "\n\n🏦 " + prod
    txt += "\n\n¿Te armo una meta para esto? Dime «quiero una meta» o «quiero comprar una congeladora»."
    return txt


def product_line(db, b: M.Business, today: date, cap: dict[str, Any] | None = None) -> str:
    cap = cap or capacity(db, b, today)
    c = cap["installment_cents"]
    if not c or c < 3000:
        return ("Para un crédito de capital de trabajo, el banco mira cuánto ganas: una cuota prudente es hasta el 30% de tu "
                "ganancia del mes (si ganas S/ 1,500, hasta S/ 450 de cuota). Registra tus ventas unas semanas, mejor cobrando por "
                "Yape, y escribe «informe»: ahí te digo cuánto te podrían prestar.")
    m6, m12 = loan_for_installment(c, 6), loan_for_installment(c, 12)
    src = "según tus ventas verificadas por Yape" if cap["source"] == "yape" else "según lo que registras (estimado)"
    return (f"Producto que te conviene: crédito para capital de trabajo, {src}. Podrías pagar una cuota de hasta {soles(c)} al mes: "
            f"un préstamo de unos {soles(m6)} a 6 meses o {soles(m12)} a 12 meses. Úsalo para comprar por volumen o equipar tu "
            "puesto, no para gastos de la casa. Escribe «informe» y llévalo al banco.")


# ------------------------------------------------------------------ préstamos
def credit_text(db, b: M.Business, today: date, amount_cents: int | None = None, months: int | None = None,
                purpose: str | None = None) -> str:
    cap = capacity(db, b, today)
    c = cap["installment_cents"]
    if amount_cents:
        n = months or 12
        cuota = installment_for_loan(amount_cents, n)
        txt = f"Un préstamo de {soles(amount_cents)} a {n} meses sería una cuota de unos {soles(cuota)} al mes (tasa referencial {int(TEA_REF * 100)}% anual). "
        if c and cuota <= c:
            txt += f"✅ Te alcanza: puedes pagar hasta {soles(c)} al mes sin ahogarte. "
        elif c:
            best = min((k for k in (6, 9, 12, 18, 24) if installment_for_loan(amount_cents, k) <= c), default=None)
            txt += (f"⚠️ Es más de lo prudente para ti (hasta {soles(c)} al mes). "
                    + (f"A {best} meses la cuota sería {soles(installment_for_loan(amount_cents, best))}, eso sí te alcanza. " if best
                       else f"Mejor pide unos {soles(loan_for_installment(c, n))} o junta una parte primero. "))
        else:
            txt += (f"Para que te alcance, tendrías que ganar al menos {soles(round(cuota / SHARE_PROFIT))} al mes (la cuota no debe pasar "
                    "del 30% de tu ganancia). Registra tus ventas unas semanas y te digo si llegas. ")
    else:
        txt = (product_line(db, b, today, cap) + " ") if c else ""
        if not c:
            txt = product_line(db, b, today, cap) + " "
    txt += ("\nAntes de pedir: compara la TCEA (el costo total) entre bancos y cajas, pide solo para algo que te haga ganar más "
            "(mercadería por volumen, equipo) y evita a los prestamistas «gota a gota».")
    if purpose:
        txt += f"\nSi quieres, primero lo armamos como meta: dime «quiero juntar {soles(amount_cents) if amount_cents else 'X'} para {purpose}»."
    return txt


# ------------------------------------------------------------------ metas
def goal_plan_text(db, b: M.Business, today: date, name: str, target_cents: int, deadline: date | None) -> str:
    cap = capacity(db, b, today)
    prof = cap["monthly_profit_cents"] or 0
    lines = []
    if deadline:
        days = max(1, (deadline - today).days)
        per_day = round(target_cents / days)
        lines.append(f"Para llegar el {deadline.day}/{deadline.month} separa {soles(per_day)} al día ({soles(per_day * 7)} a la semana).")
        if prof > 0:
            share = round(100 * per_day * 30 / prof)
            lines.append(f"Es el {share}% de lo que ganas al mes" + (" 👍." if share <= 40 else " — es bastante."))
        late = prof > 0 and per_day * 30 > prof * 0.5
    else:
        late = False
        if prof > 0:
            per_month = round(prof * 0.3)
            months = max(1, -(-target_cents // per_month))
            lines.append(f"Separando el 30% de lo que ganas ({soles(round(per_month / 30))} al día) llegas en unos {months} mes(es).")
    if not lines:
        per_day = 1000 if target_cents >= 30000 else 500
        lines.append(f"Separando {soles(per_day)} al día llegas en unos {-(-target_cents // per_day)} días.")
    if (late or not deadline) and BUSINESS_GOAL_RE.search(name.lower()) and cap["installment_cents"]:
        n = next((k for k in (6, 9, 12, 18) if installment_for_loan(target_cents, k) <= cap["installment_cents"]), None)
        if n:
            lines.append(f"🏦 Si lo necesitas antes: como es para tu negocio, un crédito de {soles(target_cents)} a {n} meses "
                         f"sería una cuota de unos {soles(installment_for_loan(target_cents, n))} (te alcanza). También puedes juntar la mitad y financiar el resto.")
    return " ".join(lines)


def goal_tips(db, b: M.Business, today: date) -> str:
    tips = ["al cerrar cada día, dime «separé 10 para mi meta»"]
    mg = sorted(_product_margins(db, b), key=lambda x: -x[2])   # lo que más deja por unidad (como en los consejos)
    if mg:
        tips.append(f"vende más {mg[0][0].lower()}, que te deja {soles(mg[0][2])} por unidad")
    rec = sum(r["pending_cents"] for r in ledger.receivables(db, b.id))
    if rec:
        tips.append(f"cobra los {soles(rec)} que te deben")
    return "Para llegar: " + "; ".join(tips[:3]) + "."
