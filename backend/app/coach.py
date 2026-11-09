"""Coach de negocios de Kallpa: asesora de negocios, consultora empresarial y coach financiera para MYPES.

Responde preguntas abiertas («¿cómo consigo más clientes?», «¿subo el precio del tomate?», «¿me conviene abrir
los domingos?», «¿debo sacar RUC?») con los números del negocio. Usa Gemini si está activo (con memoria de los
últimos mensajes) y, si no está o tarda, un consejo armado con reglas y los mismos números. Igual en app y WhatsApp.
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select

from . import ledger, metrics
from . import models as M
from .money import soles

log = logging.getLogger(__name__)

TOPICS = {
    "competencia": r"\b(competencia|competidor|competidores|la de al lado|otros puestos|me roban clientes|vecina vende|vecino vende|venden mas barato|mas barato que yo)\b",
    "precio": r"\b(precio|precios|subir|subo|bajar|bajo|cobrar mas|cobro|caro|barato|rebaja|descuento|descuentos|oferta|ofertas)\b",
    "clientes": r"\b(clientes?|caseras?|caseros?|vender mas|vendo mas|venta[s]? baja|vendo poco|atraer|fidelizar|que vuelvan|captar|conseguir clientes)\b",
    "promocion": r"\b(promocion|promociones|promo|combo|combos|yapa|regalo|sorteo|2x1|paquete)\b",
    "marketing": r"\b(publicidad|marketing|redes|facebook|instagram|tiktok|whatsapp business|catalogo|anunciar|volantes|letrero|marca|estado de whatsapp)\b",
    "formal": r"\b(ruc|sunat|formalizar|formalizarme|formal|boleta|boletas|factura|impuesto|impuestos|nrus|rus|licencia|municipal)\b",
    "ahorro": r"\b(ahorrar|ahorro|separar|separo|mezclo|plata de la casa|sueldo|pagarme|me pago|guardar plata|junta|pandero|panderos)\b",
    "inventario": r"\b(mercaderia|inventario|stock|merma|mermas|se malogra|se me malogra|vencido|vence|desperdicio|comprar mas|compro mucho|compro poco)\b",
    "delivery": r"\b(delivery|reparto|domicilio|pedidos|pedido|rappi|pedidosya|envio|envios)\b",
    "horario": r"\b(domingo|domingos|sabado|feriado|horario|abrir mas temprano|cerrar tarde|que dias|que hora|abrir)\b",
    "personal": r"\b(ayudante|trabajador|empleado|empleada|contratar|personal|sueldo del)\b",
    "proveedor": r"\b(proveedor|proveedores|mayorista|mercado mayorista|comprar barato|comprar al por mayor|al por mayor)\b",
    "crecer": r"\b(crecer|expandir|segundo puesto|otro puesto|otro local|sucursal|invertir|inversion|nuevo producto|vender otra cosa|diversificar|emprender)\b",
    "deudas": r"\b(deuda|deudas|debo mucho|atrasada|atrasado|gota a gota|prestamista|refinanciar|pagar mis deudas)\b",
}
QUESTION_START = re.compile(r"^(como|que|cual|cuales|debo|deberia|deberiamos|me conviene|conviene|es buena idea|vale la pena|"
                            r"puedo|podria|sera bueno|seria bueno|ayudame|ayudenme|dame ideas|ideas|tips|recomiendame|por que|"
                            r"cuando|donde|necesito ideas|necesito consejo|tengo un problema|tengo una duda|una consulta|"
                            r"quiero vender mas|quiero mas clientes|no vendo|vendo poco|mis ventas)\b")
SYSTEM = """Eres Kallpa, asesora de negocios, consultora empresarial y coach financiera para MYPES peruanas (bodegas,
puestos de mercado, venta de ropa, comida, servicios). Hablas con la dueña del negocio por WhatsApp, como una amiga
que sabe de negocios: tuteo cálido, español peruano sencillo, sin tecnicismos (si usas uno, lo explicas en 5 palabras).

CÓMO RESPONDES
- Respuesta corta para WhatsApp: máximo 110 palabras, en 3-5 líneas o viñetas con «•».
- Usa SIEMPRE los números del negocio que están en el CONTEXTO (productos, márgenes, días fuertes, gastos, fiados, metas,
  capacidad de crédito). No inventes cifras que no estén ahí; si falta un dato, dilo y pide que lo registre.
- Da 2 o 3 acciones concretas y baratas, y termina con «👉 Hoy:» y UNA acción para hoy.
- Si la pregunta es de precios: compara precio y costo del producto (margen) antes de recomendar.
- Si es de dinero o préstamos: solo montos referenciales del contexto (capacidad), recomienda comparar TCEA, nunca
  prestamistas «gota a gota», y préstamos solo para cosas que generen más ingresos. No prometas créditos.
- Temas de SUNAT/legales: orientación general (Nuevo RUS para negocios pequeños) y que confirme en SUNAT.
- Si no es sobre su negocio o finanzas, responde amable en una línea y vuelve a su negocio.
- No uses markdown con asteriscos ni encabezados; emojis con moderación (máximo 2).

CONTEXTO DEL NEGOCIO (datos reales registrados en Kallpa):
{ctx}"""


def topic_of(t: str) -> str | None:
    for k, pat in TOPICS.items():
        if re.search(pat, t):
            return k
    return None


ASK_ANYWHERE = re.compile(r"\b(que hago|que puedo hacer|como hago|como le hago|me conviene|deberia|debo|vale la pena|"
                          r"es buena idea|que me recomiendas|que recomiendas|ayudame|ideas para)\b")


def is_coach_question(t: str, raw_question: bool = False) -> bool:
    """¿Es una pregunta abierta de negocio? (t normalizado; raw_question = el original tenía «¿» o «?»)."""
    if not t or len(t.split()) < 2:
        return False
    if re.match(r"^(vendi|compre|gaste|pague|cobre|fie|le fie|separe|guarde|tengo \d|me pagaron|se llevo)\b", t):
        return False
    if re.match(r"^(cuanto|cuanta|cuantos|cuantas)\b", t):   # cuánto tengo / me queda / me prestarían: lo responden las reglas
        return False
    asks = raw_question or t.endswith("?") or bool(QUESTION_START.match(t)) or bool(ASK_ANYWHERE.search(t))
    return asks and topic_of(t) is not None


def looks_like_question(t: str) -> bool:
    return bool(t) and (t.endswith("?") or bool(QUESTION_START.match(t))) and len(t.split()) >= 3


# ------------------------------------------------------------------ contexto
def context(db, b: M.Business, today: date) -> dict[str, Any]:
    from . import advisor
    from .agent import business_context
    ctx = business_context(db, b)
    ctx.pop("unidades_validas", None)
    st30 = metrics.period_stats(db, b, today - timedelta(days=29), today + timedelta(days=1))
    ctx["ultimos_30_dias"] = {"ventas": st30["sales_cents"] / 100, "ganancia": st30["profit_cents"] / 100,
                              "gastos_negocio": st30["expenses_cents"] / 100, "compras_mercaderia": st30["purchases_cents"] / 100,
                              "perdidas_merma": st30.get("loss_cents", 0) / 100, "retiros_casa": st30["withdrawals_cents"] / 100,
                              "fiado_nuevo": st30["new_credit_cents"] / 100}
    ctx["margen_por_producto"] = [{"producto": n, "margen_pct": pct, "gana_por_unidad": cents / 100}
                                  for n, pct, cents in advisor._product_margins(db, b)][:12]
    try:
        top = sorted(metrics.product_margins(db, b, today - timedelta(days=29), today + timedelta(days=1)),
                     key=lambda x: -x["revenue_cents"])[:5]
        ctx["mas_vendidos_30d"] = [{"producto": x["name"], "ventas": x["revenue_cents"] / 100, "unidades": x["units"]} for x in top]
    except Exception:  # noqa: BLE001
        pass
    wp = metrics.weekday_pattern(db, b)
    if wp.get("available"):
        ctx["dias"] = {"mejor": wp["best"]["name"], "peor": wp["worst"]["name"],
                       "promedio_diario": wp["overall_avg_cents"] / 100,
                       "por_dia": {d["name"]: d["avg_sales_cents"] / 100 for d in wp["days"]}}
    ctx["gastos_declarados"] = [{"gasto": f.name, "monto": f.amount_cents / 100, "frecuencia": f.frequency or "mensual",
                                 "tipo": f.cost_type or "fijo"}
                                for f in db.scalars(select(M.FixedExpense).where(M.FixedExpense.business_id == b.id)).all()]
    cap = advisor.capacity(db, b, today)
    c = cap["installment_cents"]
    ctx["capacidad_credito"] = {"cuota_prudente_mes": c / 100, "fuente": cap["source"],
                                "prestamo_referencial_6m": advisor.loan_for_installment(c, 6) / 100 if c else 0,
                                "prestamo_referencial_12m": advisor.loan_for_installment(c, 12) / 100 if c else 0,
                                "cuotas_actuales": cap["current_installments_cents"] / 100}
    ctx["dias_con_datos"] = cap.get("days", 0)
    ctx["fecha_hoy"] = today.isoformat()
    return ctx


def _history(db, b: M.Business, channel: str, n: int = 6) -> list[dict[str, str]]:
    rows = db.scalars(select(M.ChatLog).where(M.ChatLog.business_id == b.id, M.ChatLog.channel == channel)
                      .order_by(M.ChatLog.id.desc()).limit(n + 1)).all()
    rows = list(reversed(rows))[:-1]   # sin el mensaje actual
    return [{"role": "user" if r.role == "user" else "model", "parts": [{"text": r.text[:600]}]} for r in rows if r.text]


# ------------------------------------------------------------------ respuesta
def answer(db, b: M.Business, question: str, today: date, channel: str = "web") -> str:
    from . import agent
    if agent.enabled():
        try:
            return _ai_answer(db, b, question, today, channel)
        except Exception as e:  # noqa: BLE001
            log.warning("Coach IA no disponible, respondo con reglas: %s", str(e)[:200])
    return rules_answer(db, b, question, today)


def _ai_answer(db, b: M.Business, question: str, today: date, channel: str, budget: float = 28.0) -> str:
    import httpx
    from . import agent
    from .config import settings
    ctx = json.dumps(context(db, b, today), ensure_ascii=False, default=str)
    contents = _history(db, b, channel) + [{"role": "user", "parts": [{"text": question}]}]
    body_base = {"system_instruction": {"parts": [{"text": SYSTEM.format(ctx=ctx)}]}, "contents": contents}
    t0 = time.time()
    last = None
    for model in agent.audio_model_candidates():
        left = budget - (time.time() - t0)
        if left < 5:
            break
        th = agent._thinking_by_model.get(model, {"thinkingLevel": "low"})
        gen: dict[str, Any] = {"temperature": 0.4, "maxOutputTokens": 700}
        if th:
            gen["thinkingConfig"] = th
        try:
            r = httpx.post(agent._GEN_URL.format(model), json={**body_base, "generationConfig": gen},
                           headers={"x-goog-api-key": settings.gemini_api_key}, timeout=min(20.0, left))
            if r.status_code == 400 and th:
                gen.pop("thinkingConfig", None)
                r = httpx.post(agent._GEN_URL.format(model), json={**body_base, "generationConfig": gen},
                               headers={"x-goog-api-key": settings.gemini_api_key}, timeout=min(20.0, left))
            r.raise_for_status()
            parts = r.json()["candidates"][0]["content"]["parts"]
            txt = "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()
            if txt:
                log.warning("Coach IA respondió en %.1f s con %s", time.time() - t0, model)
                return _clean(txt)
        except Exception as e:  # noqa: BLE001
            last = e
            log.warning("Coach IA (%s) falló: %s", model, str(e)[:200])
    raise RuntimeError(f"sin respuesta de la IA: {last}")


def _clean(txt: str) -> str:
    txt = re.sub(r"\*\*(.+?)\*\*", r"\1", txt)
    txt = re.sub(r"^#+\s*", "", txt, flags=re.M)
    txt = re.sub(r"^\s*[-*]\s+", "• ", txt, flags=re.M)
    return txt[:1400]


# ------------------------------------------------------------------ respaldo con reglas (sin IA)
def _mentioned_product(db, b: M.Business, t: str):
    from . import nlu
    for p in db.scalars(select(M.Product).where(M.Product.business_id == b.id, M.Product.active.is_(True))).all():
        for w in [p.name, *(p.aliases or [])]:
            if w and re.search(rf"\b{re.escape(nlu.normalize(w))}\b", t):
                return p
    return None


def rules_answer(db, b: M.Business, question: str, today: date) -> str:
    from . import advisor, nlu
    t = nlu.normalize(question)
    topic = topic_of(t) or "general"
    mg = advisor._product_margins(db, b)
    best = sorted(mg, key=lambda x: -x[2])[0] if mg else None
    wp = metrics.weekday_pattern(db, b)
    rec = sum(r["pending_cents"] for r in ledger.receivables(db, b.id))
    fixed = metrics.declared_costs(db, b)["fijo"]
    lines: list[str] = []
    hoy = ""
    if topic == "precio":
        p = _mentioned_product(db, b, t)
        if p and p.price_cents and p.cost_cents:
            m = round(100 * (p.price_cents - p.cost_cents) / p.price_cents)
            lines.append(f"{p.name}: precio {soles(p.price_cents)}, costo {soles(p.cost_cents)}, te deja {m}%.")
            if m < 25:
                lines.append(f"• Es poco margen: subir {soles(max(10, round(p.price_cents * 0.08 / 10) * 10))} casi no se nota y mejora tu ganancia.")
            else:
                lines.append("• Tu margen está sano: antes de subir, mira el precio de tus vecinas; mejor ofrécelo en combo.")
            lines.append("• Si subes, hazlo de a poco y en un producto a la vez; mira si tus ventas bajan esa semana.")
        else:
            lines.append("• Antes de cambiar un precio mira cuánto te deja: precio menos costo. Si deja menos de 25%, súbelo un poco.")
            if best:
                lines.append(f"• Tu {best[0].lower()} es lo que más te deja ({soles(best[2])} por unidad): cuídale el precio.")
        hoy = "anota el precio de 2 vecinas para tu producto principal."
    elif topic in ("clientes", "competencia"):
        if topic == "competencia":
            lines.append("• No entres a una guerra de precios: compite con frescura, atención, yapa y Yape.")
        if best:
            lines.append(f"• Ofrece primero lo que más te deja: {best[0].lower()} ({soles(best[2])} por unidad).")
        if wp.get("available"):
            lines.append(f"• Tu mejor día es {wp['best']['name']} y el más flojo {wp['worst']['name']}: ese día haz una yapa o combo.")
        lines.append("• Atiende rápido y con Yape a la vista (QR impreso): muchos clientes eligen donde pagar es fácil.")
        lines.append("• Pide el número a tus caseras y avisa por WhatsApp cuando llega mercadería fresca.")
        hoy = "pega tu QR de Yape en un lugar visible."
    elif topic in ("promocion", "marketing"):
        if len(mg) >= 2:
            lines.append(f"• Arma un combo con {mg[0][0].lower()} (te deja {mg[0][1]}%) y algo que se vende mucho: el combo sube el ticket.")
        lines.append("• Pon tus productos y precios en el estado de WhatsApp cada mañana: es gratis y lo ven tus clientes.")
        lines.append("• Una yapa pequeña a las caseras que compran seguido las hace volver.")
        hoy = "sube una foto de tu puesto con precios a tu estado de WhatsApp."
    elif topic == "formal":
        lines.append("• Para negocios pequeños existe el Nuevo RUS: pagas una cuota fija al mes y emites boletas simples.")
        lines.append("• Tener RUC te ayuda a vender a empresas y a pedir créditos con mejores condiciones.")
        lines.append("• Confirma tu categoría en SUNAT (sunat.gob.pe) o en una oficina; es un trámite gratuito.")
        hoy = "averigua en la web de SUNAT los requisitos del Nuevo RUS."
    elif topic in ("ahorro", "deudas"):
        cap = advisor.capacity(db, b, today)
        if cap["monthly_profit_cents"] and cap["monthly_profit_cents"] > 0:
            d = round(cap["monthly_profit_cents"] * 0.2 / 30 / 100) * 100 or 100
            lines.append(f"• Ganas unos {soles(cap['monthly_profit_cents'])} al mes: separa {soles(d)} cada día al cerrar (20%).")
        lines.append("• Págate un sueldo fijo para la casa y anótalo como «para la casa»: así no mezclas plata.")
        if topic == "deudas":
            lines.append("• Paga primero la deuda más cara; nunca tomes préstamos «gota a gota» para pagar otra deuda.")
        if rec:
            lines.append(f"• Te deben {soles(rec)}: cobrar eso es la plata más barata que tienes.")
        hoy = "dime al cerrar «separé 10 para mi meta»."
    elif topic == "inventario":
        st30 = metrics.period_stats(db, b, today - timedelta(days=29), today + timedelta(days=1))
        if st30.get("loss_cents"):
            lines.append(f"• Este mes perdiste {soles(st30['loss_cents'])} en merma: compra menos de lo que se malogra y véndelo primero.")
        for sv in metrics.pack_savings(db, b)[:1]:
            lines.append(f"• Comprar {sv.get('product', '').lower()} por volumen te ahorraría {soles(sv['weekly_cents'])} a la semana.")
        lines.append("• Compra según lo que vendes por día (pregúntame «¿cuánto tomate me queda?») y no por si acaso.")
        hoy = "revisa qué producto se malogra más y compra 20% menos de ese."
    elif topic == "horario":
        if wp.get("available"):
            dias = ", ".join(f"{d['name']} {soles(d['avg_sales_cents'])}" for d in wp["days"])
            lines.append(f"• Lo que vendes por día en promedio: {dias}.")
            lines.append(f"• Si abres un día más, compáralo con tu día más flojo ({wp['worst']['name']}): si vendes más que eso, conviene.")
        else:
            lines.append("• Prueba 2 o 3 semanas y registra lo que vendes ese día: si cubre tus gastos del día y deja ganancia, conviene.")
        hoy = "registra todas tus ventas de esta semana para comparar días."
    elif topic == "personal":
        cap = advisor.capacity(db, b, today)
        lines.append("• Un ayudante conviene si te libera tiempo para vender más o comprar mejor.")
        if cap["monthly_profit_cents"]:
            lines.append(f"• Hoy ganas unos {soles(cap['monthly_profit_cents'])} al mes: el pago del ayudante no debería pasar del 30% de eso.")
        lines.append("• Empieza por horas en tus días más fuertes y anota cuánto más vendes.")
        hoy = "anota cuántos clientes se van sin atender en tu día más fuerte."
    elif topic == "proveedor":
        lines.append("• Compara precios en 2 o 3 mayoristas y compra por volumen (jaba, saco, docena) lo que más vendes.")
        lines.append("• Juntarte con otras vecinas para comprar al por mayor baja el precio.")
        hoy = "pregunta el precio por jaba o saco de tu producto más vendido."
    elif topic == "crecer":
        cap = advisor.capacity(db, b, today)
        lines.append("• Crece con lo que ya te funciona: más de lo que más te deja y en tus días fuertes.")
        if fixed:
            lines.append(f"• Antes de abrir otro puesto, asegúrate de cubrir bien tus gastos fijos de hoy ({soles(fixed)} al mes).")
        if cap["installment_cents"]:
            lines.append(f"• Si necesitas plata para crecer, podrías pagar hasta {soles(cap['installment_cents'])} de cuota al mes "
                         f"(un crédito de unos {soles(advisor.loan_for_installment(cap['installment_cents'], 12))} a 12 meses).")
        hoy = "escribe «quiero una meta» y armamos tu plan para crecer."
    else:
        if not re.search(r"\b(negocio|vender|venta|ventas|ganar|ganancia|plata|dinero|caja|cliente|producto|puesto|tienda|gasto|gastos|"
                         r"costo|costos|precio|credito|prestamo|deuda|ahorro|banco|tasa|interes|margen|flujo|capital|impuesto|"
                         r"sunat|ruc|igv|mercaderia|inventario|stock|fiado)\b", t):
            lines.append("Eso se sale de lo que sé 😅, pero de tu negocio sí te puedo ayudar. Por ejemplo:")
        lines.append(advisor.advice_text(db, b, today).split("\n\n")[0].replace("💡 Mis consejos para tu negocio:\n", ""))
        hoy = "pregúntame algo más concreto, por ejemplo «¿cómo consigo más clientes?»."
    return "\n".join(lines[:4]) + f"\n👉 Hoy: {hoy}"
