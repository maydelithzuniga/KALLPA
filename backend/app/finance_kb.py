"""Preguntas teóricas de finanzas («¿qué son los gastos fijos?», «¿qué es la TCEA?», «¿qué es el leasing?»).

1) Glosario propio para MYPES: explicación sencilla + ejemplo + «En tu negocio:» con sus números (rápido y confiable).
2) Si el concepto no está: Gemini con búsqueda de Google (API que consulta fuentes de finanzas actualizadas),
   explicado sencillo y aplicado a su negocio.
3) Si la IA no responde: resumen de Wikipedia en español (API pública) + cómo aplicarlo.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, timedelta
from typing import Any, Callable

from . import ledger, metrics
from .money import soles

log = logging.getLogger(__name__)

THEORY_RE = re.compile(r"^(que es|que son|que significa|que significan|que quiere decir|a que se refiere|para que sirve|"
                       r"para que sirven|como funciona|como funcionan|como se calcula|como calculo|explicame|explica|"
                       r"cual es la diferencia|diferencia entre|en que se diferencia|define|definicion de|"
                       r"me explicas|me puedes explicar|que es eso de|y que es|y que son)\b")


def is_theory_question(t: str) -> bool:
    return bool(THEORY_RE.match(t or "")) and not re.match(r"^que es (mejor|lo que|lo mas|bueno|conveniente)\b", t or "")


def _stats(db, b, today: date) -> dict[str, Any]:
    return metrics.period_stats(db, b, today - timedelta(days=29), today + timedelta(days=1))


# ------------------------------------------------------------------ «en tu negocio» con sus números
def _fixed(db, b, today):
    from .models import FixedExpense
    rows = db.query(FixedExpense).filter(FixedExpense.business_id == b.id).all()
    fx = [r for r in rows if (r.cost_type or "fijo") == "fijo"]
    if not fx:
        return "Aún no me dijiste tus gastos fijos: dime por ejemplo «pago 250 de alquiler al mes»."
    tot = metrics.declared_costs(db, b)["fijo"]
    return f"tus gastos fijos son {', '.join(r.name.lower() for r in fx[:4])}: {soles(tot)} al mes ({soles(round(tot / 30))} al día)."


def _variable(db, b, today):
    from .models import FixedExpense
    rows = [r for r in db.query(FixedExpense).filter(FixedExpense.business_id == b.id).all() if r.cost_type == "variable"]
    base = "tu mercadería es tu principal costo variable: si vendes más, compras más."
    if rows:
        base += f" También {', '.join(r.name.lower() for r in rows[:3])}."
    return base


def _margin(db, b, today):
    from .advisor import _product_margins
    mg = _product_margins(db, b)
    if not mg:
        return "dime precio y costo de tus productos para calcularlo."
    return "; ".join(f"{n.lower()} te deja {p}%" for n, p, _ in mg[:3]) + "."


def _profit(db, b, today):
    st = _stats(db, b, today)
    return f"en los últimos 30 días vendiste {soles(st['sales_cents'])} y ganaste {soles(st['profit_cents'])}."


def _cash(db, b, today):
    from .summaries import explain
    return explain(db, b, "flujo").replace("Es la plata que de verdad tienes en la mano para usar. ", "")


def _working(db, b, today):
    cash = metrics.cash_position(db, b)
    inv = sum(i["stock_value_cents"] or 0 for i in metrics.inventory(db, b))
    rec = sum(r["pending_cents"] for r in ledger.receivables(db, b.id))
    return (f"tienes {soles(cash['total_cents'])} en caja, unos {soles(inv)} en mercadería y {soles(rec)} por cobrar. "
            "Esa es la plata con la que tu negocio se mueve día a día.")


def _break_even(db, b, today):
    from .summaries import explain
    return explain(db, b, "equilibrio").replace("Es lo mínimo que tienes que vender para no perder: lo que cubre tus gastos fijos del mes. ", "")


def _credit(db, b, today):
    from .advisor import capacity, loan_for_installment
    c = capacity(db, b, today)["installment_cents"]
    if not c:
        return "registra tus ventas unas semanas y te digo qué cuota podrías pagar."
    return f"podrías pagar una cuota de hasta {soles(c)} al mes: un préstamo de unos {soles(loan_for_installment(c, 12))} a 12 meses."


def _receivable(db, b, today):
    rec = ledger.receivables(db, b.id)
    tot = sum(r["pending_cents"] for r in rec)
    return f"te deben {soles(tot)}" + (f" ({', '.join(r['counterparty'] for r in rec[:3])})." if rec else ".")


def _inventory(db, b, today):
    inv = [i for i in metrics.inventory(db, b) if i["track_stock"] and i["expected_stock"] is not None]
    val = sum(i["stock_value_cents"] or 0 for i in inv)
    return f"tienes unos {soles(val)} en mercadería." if inv else "dime cuánto te queda de cada producto para llevar tu inventario."


def _loss(db, b, today):
    st = _stats(db, b, today)
    return f"este mes perdiste {soles(st.get('loss_cents', 0))} en mercadería malograda o perdida."


def _savings(db, b, today):
    from .advisor import capacity
    p = capacity(db, b, today)["monthly_profit_cents"]
    if p and p > 0:
        return f"si ganas unos {soles(p)} al mes, ahorrar el 20% es {soles(round(p * 0.2))} al mes ({soles(round(p * 0.2 / 30))} al día)."
    return "empieza separando aunque sea S/ 5 al día al cerrar."


def _sales(db, b, today):
    st = _stats(db, b, today)
    n = max(1, st.get("sales_count", 0) or 1)
    return f"en 30 días hiciste {st.get('sales_count', 0)} ventas por {soles(st['sales_cents'])}: unos {soles(round(st['sales_cents'] / n))} por venta."


def _none(db, b, today):
    return ""


# clave: (patrón, título, explicación sencilla, ejemplo, función «en tu negocio»)
GLOSSARY: list[tuple[str, str, str, str, Callable]] = [
    (r"gastos? fijos?|costos? fijos?", "Gastos fijos",
     "Son los pagos que haces igual, vendas mucho o poco: alquiler del puesto, luz, celular, sueldo del ayudante.",
     "Si un día no vendes nada, el alquiler igual se paga.", _fixed),
    (r"gastos? variables?|costos? variables?|y variables?|variables", "Gastos variables",
     "Son los que suben o bajan según cuánto vendes: la mercadería, las bolsas, el flete.",
     "Si vendes el doble de tomate, compras el doble de tomate y usas el doble de bolsas.", _variable),
    (r"costo de venta|costo de lo vendido|costo de mercaderia", "Costo de venta",
     "Es lo que te costó la mercadería que vendiste (no toda la que compraste).",
     "Vendiste 10 kilos que te costaron S/ 2 cada uno: tu costo de venta es S/ 20.", _margin),
    (r"margen|margen de ganancia|margen de contribucion", "Margen",
     "Es lo que te queda de cada venta después de pagar lo que te costó el producto.",
     "Vendes a S/ 3 lo que te costó S/ 2: tu margen es S/ 1 (33%).", _margin),
    (r"ganancia|utilidad|ganancia neta|utilidad neta|ganancia bruta|utilidad bruta|rentabilidad", "Ganancia (utilidad)",
     "Es lo que te queda de verdad: lo que vendiste menos lo que te costó la mercadería y menos tus gastos del negocio. "
     "La rentabilidad es cuánto ganas por cada sol que vendes o inviertes.",
     "Vendiste S/ 1,000, la mercadería costó S/ 600 y gastaste S/ 200: ganaste S/ 200 (20% de rentabilidad).", _profit),
    (r"flujo de caja|flujo de efectivo|cash flow", "Flujo de caja",
     "Es la plata que entra y sale de verdad de tu bolsillo y tu Yape. No es lo mismo que ganancia: si vendes fiado, "
     "ganas pero la plata todavía no entra.",
     "Vendiste S/ 100 pero S/ 30 fueron fiados: solo te entraron S/ 70.", _cash),
    (r"capital de trabajo|capital de trabajo neto", "Capital de trabajo",
     "Es la plata que tu negocio necesita para moverse día a día: caja, mercadería y lo que te deben, menos lo que tú debes.",
     "Sin capital de trabajo no puedes comprar la jaba del lunes aunque el negocio gane.", _working),
    (r"punto de equilibrio", "Punto de equilibrio",
     "Es lo mínimo que tienes que vender para no perder: con eso cubres tus gastos fijos. Lo que vendas encima ya es ganancia.",
     "Si tus gastos fijos son S/ 600 al mes y de cada sol te quedan 40 céntimos, necesitas vender S/ 1,500 al mes.", _break_even),
    (r"liquidez", "Liquidez",
     "Es tener plata disponible para pagar lo de hoy. Un negocio puede ganar y aun así no tener liquidez si todo está en mercadería o fiados.",
     "Tienes S/ 2,000 en mercadería pero solo S/ 50 en caja: tienes poca liquidez.", _working),
    (r"rotacion|rotacion de inventario", "Rotación",
     "Es qué tan rápido vendes tu mercadería y la vuelves plata. Más rotación = la plata trabaja más veces.",
     "Si compras el lunes y vendes todo el miércoles, rotas rápido.", _inventory),
    (r"inventario|stock", "Inventario",
     "Es la mercadería que tienes para vender. Es plata guardada: si se malogra o no se vende, pierdes.",
     "10 kilos de papa a S/ 1.80 son S/ 18 en inventario.", _inventory),
    (r"merma|mermas", "Merma",
     "Es la mercadería que pierdes: se malogra, se vence, se rompe o se pierde. Es plata que se va sin venderse.",
     "Si se malogran 2 kilos de tomate de S/ 2, perdiste S/ 4.", _loss),
    (r"cuentas por cobrar|fiado|fiados|credito a clientes", "Cuentas por cobrar (fiados)",
     "Es la plata que tus clientes te deben. Ya vendiste, pero la plata todavía no está contigo.",
     "Rosa se llevó S/ 20 fiado: tienes S/ 20 por cobrar.", _receivable),
    (r"cuentas por pagar", "Cuentas por pagar",
     "Es lo que tú debes: al proveedor que te fió, cuotas de préstamos, alquiler pendiente.",
     "Te fiaron la jaba de S/ 40 hasta el viernes: tienes S/ 40 por pagar.", _none),
    (r"activos?", "Activo",
     "Es todo lo que tiene tu negocio y vale plata: caja, Yape, mercadería, lo que te deben, tu balanza, tu congeladora.",
     "Tu balanza de S/ 300 es un activo.", _working),
    (r"pasivos?", "Pasivo",
     "Es todo lo que tu negocio debe: préstamos, cuotas, lo que debes al proveedor.",
     "Si debes S/ 1,000 al banco, tienes S/ 1,000 de pasivo.", _none),
    (r"patrimonio|capital propio", "Patrimonio",
     "Es lo que de verdad es tuyo en el negocio: lo que tienes (activos) menos lo que debes (pasivos).",
     "Tienes S/ 3,000 en cosas y plata, y debes S/ 1,000: tu patrimonio es S/ 2,000.", _none),
    (r"tcea|costo efectivo anual", "TCEA (Tasa de Costo Efectivo Anual)",
     "Es cuánto te cuesta DE VERDAD un préstamo en un año: incluye la tasa de interés más seguros, comisiones y gastos. "
     "Es el número que debes comparar entre bancos y cajas: la TCEA más baja es la más barata.",
     "Dos préstamos con la misma tasa pueden tener distinta TCEA por los seguros.", _credit),
    (r"tea|tasa efectiva anual|tasa de interes|interes|intereses", "Tasa de interés (TEA)",
     "Es el precio que pagas por usar plata prestada, contado por año. La TEA no incluye seguros ni comisiones; la TCEA sí.",
     "Un préstamo de S/ 1,000 al 40% TEA te cuesta unos S/ 400 de interés en un año (menos si pagas en cuotas).", _credit),
    (r"cuota|cuotas", "Cuota",
     "Es lo que pagas cada mes (o semana) para devolver un préstamo: una parte es lo prestado y otra el interés.",
     "Un préstamo de S/ 2,000 a 12 meses puede ser una cuota de unos S/ 200.", _credit),
    (r"credito|prestamo|financiamiento", "Crédito (préstamo)",
     "Es plata que te prestan y devuelves en cuotas con interés. Conviene si la usas para algo que te haga ganar más "
     "que lo que pagas de interés (mercadería por volumen, equipo).",
     "Pides S/ 1,000 para comprar por saco y ahorras S/ 150 al mes: si la cuota de interés es menor, te conviene.", _credit),
    (r"central de riesgo|centrales de riesgo|infocorp|sentinel|historial crediticio|calificacion crediticia|score", "Central de riesgo / historial crediticio",
     "Es el registro de cómo pagas tus deudas (en el Perú lo lleva la SBS y empresas como Infocorp o Sentinel). "
     "Si pagas a tiempo, tu calificación es «Normal» y te prestan más y más barato; si te atrasas, te cierran puertas.",
     "Pagar puntual un préstamo chiquito es la mejor forma de construir historial.", _credit),
    (r"garantia|aval|garante", "Garantía / aval",
     "Es lo que respalda un préstamo si no lo pagas: un bien (garantía) o una persona que paga por ti (aval).",
     "Algunos créditos para MYPES no piden garantía si tienes buen historial y ventas registradas.", _none),
    (r"sobreendeudamiento|sobre endeudamiento|endeudamiento", "Sobreendeudamiento",
     "Es deber más de lo que puedes pagar con lo que ganas. Señal de alarma: tus cuotas pasan del 30-40% de lo que ganas al mes.",
     "Si ganas S/ 1,500 al mes y pagas S/ 900 en cuotas, estás sobreendeudada.", _credit),
    (r"gota a gota|prestamista|prestamistas informales|usura", "Préstamo «gota a gota»",
     "Son préstamos informales con intereses altísimos (a veces 20% al mes o más) y cobros con amenazas. Evítalos: "
     "mejor una caja municipal, cooperativa o banco regulado por la SBS.",
     "S/ 1,000 «gota a gota» pueden costarte S/ 200 de interés en un solo mes.", _none),
    (r"ahorro|ahorrar", "Ahorro",
     "Es separar una parte de lo que ganas antes de gastarla, para una meta o para emergencias.",
     "Separar S/ 10 al día son S/ 300 al mes.", _savings),
    (r"interes compuesto", "Interés compuesto",
     "Es cuando los intereses también generan intereses. Te ayuda si ahorras y te perjudica si te atrasas en una deuda.",
     "Si dejas S/ 1,000 al 5% anual, el segundo año ganas interés también sobre los S/ 50 del primero.", _savings),
    (r"inflacion", "Inflación",
     "Es cuando las cosas suben de precio con el tiempo y tu plata alcanza para menos.",
     "Si el aceite sube de S/ 8 a S/ 9, con la misma plata compras menos.", _margin),
    (r"presupuesto", "Presupuesto",
     "Es un plan de cuánto vas a vender, comprar y gastar en un periodo, para no quedarte sin plata.",
     "Este mes: vender S/ 3,000, comprar S/ 1,800, gastos S/ 600, ahorrar S/ 300.", _fixed),
    (r"inversion|invertir", "Inversión",
     "Es usar plata hoy en algo que te va a dar más plata después: una congeladora, más mercadería, un mejor puesto.",
     "Una congeladora de S/ 1,500 que te permite vender S/ 300 más al mes se paga en pocos meses.", _credit),
    (r"depreciacion", "Depreciación",
     "Es lo que pierde de valor un equipo con el uso y el tiempo. Sirve para ir guardando y reemplazarlo.",
     "Una balanza de S/ 300 que dura 3 años pierde unos S/ 100 de valor por año.", _none),
    (r"ticket promedio", "Ticket promedio",
     "Es cuánto te compra en promedio cada cliente. Si lo subes (con combos o yapa), vendes más sin más clientes.",
     "100 ventas por S/ 500 = ticket promedio de S/ 5.", _sales),
    (r"igv", "IGV (Impuesto General a las Ventas)",
     "Es el impuesto de 18% que va incluido en el precio de lo que se vende. En el Nuevo RUS no lo declaras aparte: "
     "pagas una cuota fija mensual.",
     "Si vendes con factura S/ 118, S/ 18 son de IGV.", _none),
    (r"ruc|nuevo rus|rus|rer|regimen tributario|regimen mype|mype tributario", "RUC y regímenes tributarios",
     "El RUC es tu número de contribuyente en SUNAT. Para negocios pequeños existe el Nuevo RUS: pagas una cuota fija al mes "
     "según cuánto vendes y das boletas simples. Si creces, hay otros regímenes (RER, Régimen MYPE). Confirma tu caso en SUNAT.",
     "Con RUC puedes vender a empresas y acceder a créditos con mejores condiciones.", _sales),
    (r"boleta|factura|comprobante", "Boleta y factura",
     "Son comprobantes de venta. La boleta es para personas; la factura para empresas que la usan para sus impuestos.",
     "En el Nuevo RUS solo das boletas (no facturas).", _none),
    (r"leasing|arrendamiento financiero", "Leasing (arrendamiento financiero)",
     "Es como alquilar un equipo pagando cuotas, y al final puedes quedarte con él pagando un monto pequeño. "
     "Sirve para equipos caros (congeladora, moto, máquina) sin pagar todo de golpe.",
     "Una congeladora de S/ 3,000 en leasing a 24 meses: pagas cuotas y al final es tuya.", _credit),
    (r"factoring|factorizacion", "Factoring",
     "Es vender tus facturas por cobrar a un banco o empresa para recibir la plata ya, a cambio de un descuento. "
     "Sirve si le vendes a empresas que te pagan a 30 o 60 días.",
     "Tienes una factura de S/ 1,000 a 60 días: te adelantan S/ 970 hoy.", _receivable),
    (r"linea de credito", "Línea de crédito",
     "Es un monto aprobado que puedes usar cuando lo necesites y pagas interés solo por lo que usas.",
     "Te aprueban S/ 2,000; usas S/ 500 para mercadería y pagas interés solo por esos S/ 500.", _credit),
    (r"tarjeta de credito", "Tarjeta de crédito",
     "Es plata prestada para pagar con tarjeta. Si pagas el total del mes no pagas interés; si pagas el mínimo, el interés es muy alto.",
     "Comprar mercadería con tarjeta y pagar solo el mínimo puede salir más caro que un crédito de capital de trabajo.", _credit),
    (r"refinanciamiento|refinanciar|reprogramacion|reprogramar", "Refinanciar / reprogramar",
     "Es cambiar las condiciones de una deuda (más plazo, otra cuota) cuando no puedes pagarla como estaba. "
     "Ayuda a no caer en mora, pero puede bajar tu calificación: pídelo antes de atrasarte.",
     "Pasar una deuda de 6 a 12 meses baja la cuota, pero pagas más interés en total.", _credit),
    (r"periodo de gracia", "Periodo de gracia",
     "Son meses al inicio de un préstamo en los que no pagas la cuota (o solo intereses). Útil si el préstamo tarda en dar frutos.",
     "Compras una congeladora y empiezas a pagar cuando ya vendes helados.", _credit),
    (r"caja municipal|cajas municipales|cooperativa|cooperativas|financiera|financieras|microfinanciera", "Cajas, cooperativas y financieras",
     "Son entidades que prestan y guardan plata, muchas especializadas en pequeños negocios. Elige las supervisadas por la SBS "
     "(o la SBS/FENACREP en cooperativas) y compara siempre la TCEA.",
     "Una caja municipal puede prestarte para capital de trabajo con tu historial de ventas.", _credit),
    (r"seguro|microseguro|seguros", "Seguro",
     "Pagas un poquito cada mes para que, si pasa algo (robo, incendio, enfermedad), te cubran una pérdida grande.",
     "Un microseguro de S/ 10 al mes puede cubrir la mercadería de tu puesto.", _savings),
]


def glossary_answer(db, b, t: str, today: date) -> str | None:
    hits = []
    for pat, title, expl, ex, fn in GLOSSARY:
        m = re.search(rf"\b({pat})\b", t)
        if m:
            hits.append((m.start(), -len(m.group(0)), (pat, title, expl, ex, fn)))
    if not hits:
        return None
    hits.sort()
    chosen = [h[2] for h in hits[:2]] if re.search(r"\b(diferencia|vs|versus|o)\b", t) else [hits[0][2]]
    parts = []
    for _pat, title, expl, ex, fn in chosen:
        try:
            yours = fn(db, b, today)
        except Exception:   # noqa: BLE001
            yours = ""
        txt = f"📘 {title}: {expl}\nEjemplo: {ex}"
        if yours:
            txt += f"\nEn tu negocio: {yours[0].upper() + yours[1:]}"
        parts.append(txt)
    return "\n\n".join(parts)


# ------------------------------------------------------------------ concepto que no está en el glosario
def _concept(t: str) -> str:
    c = THEORY_RE.sub("", t).strip()
    c = re.sub(r"^(el|la|los|las|un|una|eso de|lo de)\s+", "", c)
    return c.strip(" ?")


def ai_theory(db, b, question: str, today: date, budget: float = 25.0) -> str:
    """Gemini con búsqueda de Google: explica el concepto sencillo y lo aplica al negocio."""
    import time
    import httpx
    from . import agent
    from .coach import context
    from .config import settings
    if not agent.enabled():
        raise RuntimeError("IA desactivada")
    ctx = json.dumps(context(db, b, today), ensure_ascii=False, default=str)[:6000]
    sys = ("Eres Kallpa, coach financiera de MYPES peruanas. Explica conceptos de finanzas y negocios a una emprendedora "
           "con palabras muy sencillas (como a una amiga), en máximo 90 palabras: 1) qué es, en una o dos frases; 2) un ejemplo "
           "con soles y cosas de su negocio; 3) «En tu negocio:» cómo se aplica con sus números del CONTEXTO (no inventes). "
           "Usa información confiable y actual del Perú (SBS, SUNAT, BCRP) si aplica. Sin markdown ni asteriscos.\n\nCONTEXTO:\n" + ctx)
    body = {"system_instruction": {"parts": [{"text": sys}]},
            "contents": [{"role": "user", "parts": [{"text": question}]}],
            "tools": [{"google_search": {}}],
            "generationConfig": {"temperature": 0.3, "maxOutputTokens": 600}}
    t0 = time.time()
    last = None
    for model in agent.audio_model_candidates():
        left = budget - (time.time() - t0)
        if left < 5:
            break
        for use_tools in (True, False):   # si el modelo no acepta búsqueda, sin búsqueda
            b2 = dict(body) if use_tools else {k: v for k, v in body.items() if k != "tools"}
            try:
                r = httpx.post(agent._GEN_URL.format(model), json=b2, headers={"x-goog-api-key": settings.gemini_api_key},
                               timeout=min(20.0, left))
                if r.status_code == 400 and use_tools:
                    continue
                r.raise_for_status()
                parts = r.json()["candidates"][0]["content"]["parts"]
                txt = "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()
                if txt:
                    from .coach import _clean
                    log.warning("Teoría con IA en %.1f s (%s, búsqueda=%s)", time.time() - t0, model, use_tools)
                    return "📘 " + _clean(txt)
            except Exception as e:  # noqa: BLE001
                last = e
                log.warning("Teoría IA (%s) falló: %s", model, str(e)[:200])
                break
    raise RuntimeError(f"sin respuesta: {last}")


def wikipedia_theory(question: str, timeout: float = 8.0) -> str | None:
    """Resumen de Wikipedia en español (API pública, sin clave)."""
    import httpx
    concept = _concept(question)
    if not concept or len(concept) < 3:
        return None
    try:
        h = {"User-Agent": "Kallpa/1.0 (asistente financiero para MYPES)"}
        s = httpx.get("https://es.wikipedia.org/w/api.php", params={"action": "query", "list": "search", "srsearch": concept + " economía",
                                                                   "format": "json", "srlimit": 1}, headers=h, timeout=timeout)
        s.raise_for_status()
        res = s.json().get("query", {}).get("search", [])
        if not res:
            return None
        title = res[0]["title"]
        r = httpx.get(f"https://es.wikipedia.org/api/rest_v1/page/summary/{title.replace(' ', '_')}", headers=h, timeout=timeout)
        r.raise_for_status()
        ext = r.json().get("extract", "")
        sent = re.split(r"(?<=[.!?])\s+", ext)
        short = " ".join(sent[:2])[:420]
        return f"📘 {title}: {short}" if short else None
    except Exception as e:  # noqa: BLE001
        log.warning("Wikipedia no respondió: %s", e)
        return None


def answer(db, b, question: str, today: date) -> str:
    from . import nlu
    t = nlu.normalize(question)
    g = glossary_answer(db, b, t, today)
    if g:
        return g
    try:
        return ai_theory(db, b, question, today)
    except Exception as e:  # noqa: BLE001
        log.warning("Teoría sin IA: %s", e)
    w = wikipedia_theory(question)
    if w:
        return w + "\nEn tu negocio: si quieres, pregúntame cómo aplicarlo, por ejemplo «¿me conviene para mi puesto?»."
    return ("No tengo ese concepto a la mano 😅. Pregúntamelo con otras palabras o pregúntame por: gastos fijos, margen, "
            "flujo de caja, capital de trabajo, TCEA, central de riesgo, IGV o Nuevo RUS.")
