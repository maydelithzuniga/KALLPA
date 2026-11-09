"""Motor de conversación compartido por el chat web y WhatsApp.

audio → transcripción → borrador → aclaración (una pregunta por turno) → confirmación → registro.
"""
from __future__ import annotations

import re
import uuid
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import ledger, metrics, nlu, reconcile, setup, summaries
from . import models as M
from .money import soles
from .textutil import pluralize
from .timeutil import add_months, month_label, month_start, now_lima, today_lima

NUM_WORDS = ["cero", "un", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve", "diez", "once",
             "doce", "trece", "catorce", "quince", "dieciséis", "diecisiete", "dieciocho", "diecinueve", "veinte"]

MOVEMENT_LABEL = {
    M.SALE: "venta", M.PURCHASE: "compra", M.EXPENSE: "gasto", M.WITHDRAWAL: "retiro para la casa",
    M.CONTRIBUTION: "aporte propio", M.TRANSFER: "traslado", M.COLLECTION: "cobro de fiado",
    M.DEBT_PAYMENT: "pago de cuota", M.OPENING: "saldo inicial", M.STOCK_ADJ: "ajuste de stock",
    M.GOAL_SAVING: "ahorro para meta",
}


def qty_name(qty: int | None, name: str) -> str:
    name = name.lower()
    if not qty:
        return name
    if qty == 1:
        art = "una" if name.split()[0].endswith("a") else "un"
        return f"{art} {name}"
    q = NUM_WORDS[qty] if qty <= 20 else str(qty)
    return f"{q} {pluralize(name)}"


def cap(s: str) -> str:
    return s[:1].upper() + s[1:] if s else s


def method_txt(m: str | None) -> str:
    return {"yape": "por Yape", "efectivo": "en efectivo"}.get(m or "", "")


def _m(method: str | None) -> str:
    t = method_txt(method)
    return f" {t}" if t else ""


class Engine:
    def __init__(self, db: Session, business: M.Business, conversation: str, channel: str = "web"):
        self.db = db
        self.b = business
        self.conv = conversation
        self.channel = channel
        self.today = today_lima()

    # ------------------------------------------------------------ utilidades
    def products(self) -> list[nlu.ProductRef]:
        return [nlu.ProductRef(p.id, p.name, p.aliases or [], p.price_cents, p.cost_cents, p.track_stock,
                               p.is_input, p.is_service)
                for p in self.db.scalars(select(M.Product).where(M.Product.business_id == self.b.id,
                                                                 M.Product.active.is_(True))).all()]

    def open_draft(self) -> M.Draft | None:
        return self.db.scalar(select(M.Draft).where(M.Draft.business_id == self.b.id, M.Draft.conversation == self.conv,
                                                    M.Draft.status == "abierto").order_by(M.Draft.id.desc()))

    def new_draft(self, action: str, data: dict[str, Any]) -> M.Draft:
        for d in self.db.scalars(select(M.Draft).where(M.Draft.business_id == self.b.id, M.Draft.conversation == self.conv,
                                                       M.Draft.status == "abierto")).all():
            d.status = "cancelado"
        d = M.Draft(business_id=self.b.id, conversation=self.conv, op_id=uuid.uuid4().hex, action=action, data=data)
        self.db.add(d)
        self.db.flush()
        return d

    def resp(self, reply: str, draft: M.Draft | None = None, quick: list[str] | None = None,
             movement: M.Movement | None = None, **extra) -> dict[str, Any]:
        out = {"reply": reply, "quick_replies": quick or [], "draft": self.draft_view(draft) if draft else None,
               "movement": movement_view(self.db, movement) if movement else None,
               "updated_at": now_lima().isoformat()}
        out.update(extra)
        return out

    def draft_view(self, d: M.Draft) -> dict[str, Any]:
        return {"op_id": d.op_id, "action": d.action, "missing": d.missing, "options": d.options,
                "data": d.data, "status": d.status}

    # ------------------------------------------------------------ entrada
    def handle(self, text: str, *, op_id: str | None = None, occurred_at: datetime | None = None) -> dict[str, Any]:
        text = (text or "").strip()
        if self.b.setup_state != "listo":
            return self.onboarding(text)
        parsed = nlu.parse(text, self.products(), self.today)
        draft = self.open_draft()

        if op_id:
            d_any = self.db.scalar(select(M.Draft).where(M.Draft.op_id == op_id))
            if d_any and d_any.status == "confirmado":
                mv = ledger.find_movement_by_op(self.db, op_id)
                return self.resp("Eso ya está guardado, no lo dupliqué.", movement=mv, duplicate=True)
            if d_any and d_any.status == "cancelado":
                return self.resp("Ese registro ya fue cancelado.")
            if d_any:
                draft = d_any

        if parsed.intent == "consentir_informe" or (
                re.match(r"^(si )?(envialo|mandalo|enviale|mandale)\b", nlu.normalize(text)) and self.pending_consent_month()):
            return self.consent(True, draft if draft and draft.action == "consentimiento" else None)
        if draft and draft.action == "consentimiento":
            if parsed.intent == "confirmar":
                return self.consent(True, draft)
            if parsed.intent == "cancelar" or nlu.normalize(text).startswith("no por ahora"):
                return self.consent(False, draft)
            draft.status = "cancelado"   # siguió con otra cosa: no insistimos este mes
            self.db.flush()
            draft = None
        if draft:
            r = self.continue_draft(draft, parsed, text, occurred_at)
            if r is not None:
                return self.with_consent_prompt(r)
        return self.with_consent_prompt(self.fresh(parsed, text, occurred_at))

    def fresh(self, p: nlu.Parsed, raw: str, occurred_at: datetime | None) -> dict[str, Any]:
        i = p.intent
        if i == "confirmar":
            return self.resp("No tengo nada pendiente por guardar. Cuéntame qué vendiste o gastaste.")
        if i == "cancelar":
            return self.resp("Ok, no hay nada pendiente.")
        if i == "movimiento":
            data = dict(p.fields)
            data["raw_text"] = raw
            data["occurred_at"] = self._when(data, occurred_at)
            d = self.new_draft("movimiento", data)
            return self.step(d)
        if i == "catalogo":
            d = self.new_draft("catalogo", dict(p.fields))
            return self.step(d)
        if i == "saldo_inicial":
            bal = p.fields.get("balances") or {}
            if not bal:
                return self.resp("¿Con cuánto empiezas en efectivo y en Yape?")
            d = self.new_draft("saldo", {"balances": bal})
            return self.step(d)
        if i == "conteo_stock":
            d = self.new_draft("conteo", {"kind": "stock", **p.fields})
            return self.step(d)
        if i == "conteo_caja":
            c = reconcile.cash_count(self.db, self.b, p.fields["pocket"], p.fields["counted_cents"])
            return self.resp(reconcile.count_text(self.db, c), count=metrics._count_dict(c))
        if i == "meta":
            d = self.new_draft("meta", dict(p.fields))
            return self.step(d)
        if i == "ahorro_meta":
            d = self.new_draft("movimiento", {"kind": M.GOAL_SAVING, **p.fields, "raw_text": raw,
                                              "occurred_at": self._when(p.fields, occurred_at)})
            return self.step(d)
        if i == "corregir":
            return self.start_correction(p)
        if i == "anular":
            mv = self.last_movement()
            if not mv:
                return self.resp("No encontré un movimiento para anular.")
            d = self.new_draft("anulacion", {"movement_id": mv.id})
            d.summary_read = True
            return self.resp(f"¿Anulo tu {MOVEMENT_LABEL[mv.kind]}: {describe_movement(self.db, mv)}?", d, ["Sí, anular", "No"])
        if i == "consentir_informe":
            return self.consent(True)
        return self.answer_question(i)

    def _when(self, fields: dict[str, Any], occurred_at: datetime | None) -> str:
        if fields.get("day"):
            d = date.fromisoformat(fields["day"])
            base = occurred_at or now_lima()
            return datetime(d.year, d.month, d.day, base.hour, base.minute).isoformat()
        return (occurred_at or now_lima()).isoformat()

    # ------------------------------------------------------------ preguntas
    def answer_question(self, intent: str) -> dict[str, Any]:
        db, b = self.db, self.b
        if intent == "resumen_dia":
            return self.resp(summaries.daily(db, b))
        if intent == "resumen_semana":
            return self.resp(summaries.weekly(db, b))
        if intent == "resumen_mes":
            return self.resp(summaries.monthly(db, b))
        if intent == "caja":
            return self.resp(summaries.cash_line(db, b))
        if intent == "reponer":
            gs = [g for g in metrics.goals(db, b) if g["kind"] == "reposicion" and g["status"] == "activa"]
            if gs:
                return self.resp(gs[0]["message"])
            cash = metrics.cash_position(db, b)
            if cash["available_for_restock_cents"] is None:
                return self.resp(cash["missing_text"])
            return self.resp(f"Según tu caja y tus pagos registrados, hoy puedes usar {soles(max(0, cash['available_for_restock_cents']))} para reponer. "
                             "Dime «quiero reponer mercadería por 200» y lo sigo como meta.")
        if intent == "consejos":
            tips = metrics.advice(db, b)
            return self.resp(" ".join(tips[:2]))
        if intent.startswith("explica_"):
            return self.resp(summaries.explain(db, b, intent.split("_", 1)[1]))
        if intent == "fiados":
            return self.resp(summaries.receivables_text(db, b))
        if intent == "metas":
            return self.resp(summaries.goals_text(db, b))
        if intent == "inventario":
            return self.resp(summaries.inventory_text(db, b))
        if intent == "informe":
            return self.resp("Tu informe para el banco está en la app, en «Reporte». Lo revisas y decides si lo descargas y lo presentas.")
        if intent == "ayuda":
            name = f" {self.b.owner_name}" if self.b.owner_name else ""
            return self.resp(f"¡Hola{name}! " + summaries.HELP)
        return self.resp("No te entendí bien. " + summaries.HELP, quick=["Resumen de hoy", "¿Cuánto tengo?"])

    # ------------------------------------------------------------ borradores
    def continue_draft(self, d: M.Draft, p: nlu.Parsed, raw: str, occurred_at) -> dict[str, Any] | None:
        if p.intent == "confirmar":
            return self.confirm(d)
        if p.intent == "cancelar":
            d.status = "cancelado"
            self.db.commit()
            return self.resp("Listo, no lo guardé.")
        new_movement = p.intent in ("movimiento", "catalogo", "meta", "saldo_inicial", "conteo_stock", "conteo_caja",
                                    "corregir", "anular", "ahorro_meta") and not raw.lower().startswith("no")
        if new_movement and d.missing and not self._substantive(p):
            new_movement = False
        if new_movement and not (d.missing and p.intent == "movimiento" and self._answers_missing(d, p)):
            d.status = "cancelado"
            self.db.flush()
            return None
        if p.intent.startswith(("resumen", "explica", "caja", "fiados", "metas", "inventario", "consejos", "reponer", "ayuda")) \
                and p.intent != "valor":
            r = self.answer_question(p.intent)
            r["reply"] += " (Sigo esperando tu respuesta sobre lo anterior.)"
            r["draft"] = self.draft_view(d)
            return r
        changed = self.apply_answer(d, p, raw)
        if not changed:
            q = self.step(d, reask=True)
            return q
        if d.data.get("paid_cents") == 0 and d.missing == "method":
            return self.step(d)
        # Si ya se leyó el resumen y solo faltaba el medio de pago, la respuesta completa y confirma
        auto = d.missing == "method" and d.summary_read and d.data.get("method") in M.POCKETS
        res = self.step(d, auto_confirm=auto)
        return res

    @staticmethod
    def _substantive(p: nlu.Parsed) -> bool:
        f = p.fields
        keys = ("product_candidates", "new_product", "total_cents", "amount_cents", "ambiguous_price_cents",
                "unit_price_cents", "ambiguous_cents", "price_cents", "cost_cents", "counted", "counted_cents",
                "target_cents", "balances", "stock")
        return any(f.get(k) for k in keys)

    def _answers_missing(self, d: M.Draft, p: nlu.Parsed) -> bool:
        return d.missing in ("method",) and "method" in p.fields and len(p.text.split()) <= 4

    def apply_answer(self, d: M.Draft, p: nlu.Parsed, raw: str) -> bool:
        data = dict(d.data)
        f = p.fields
        changed = False
        miss = d.missing
        if miss == "product" and d.options:
            choice = None
            if f.get("option_index") and 1 <= f["option_index"] <= len(d.options):
                choice = d.options[f["option_index"] - 1]
            else:
                t = nlu.normalize(raw)
                for opt in d.options:
                    words = [w for w in nlu.normalize(opt["name"]).split() if len(w) > 2]
                    if any(w in t.split() for w in words[1:] or words):
                        choice = opt
                        break
                if not choice and f.get("product_candidates"):
                    ids = [o["id"] for o in d.options]
                    inter = [c for c in f["product_candidates"] if c in ids]
                    if len(inter) == 1:
                        choice = next(o for o in d.options if o["id"] == inter[0])
            if choice:
                data["product_candidates"] = [choice["id"]]
                changed = True
        elif miss == "price_role":
            role = f.get("price_role")
            t = nlu.normalize(raw)
            if not role:
                if "total" in t or "todo" in t:
                    role = "total"
                elif "cada" in t or "unidad" in t or "uno" in t:
                    role = "unidad"
            if role:
                amb = data.pop("ambiguous_price_cents")
                if role == "total":
                    data["total_cents"] = amb
                else:
                    data["unit_price_cents"] = amb
                changed = True
        elif miss == "catalog_role":
            role = f.get("catalog_role")
            t = nlu.normalize(raw)
            if not role:
                if any(w in t for w in ("vendo", "cobro", "venta", "precio")):
                    role = "precio"
                elif any(w in t for w in ("compro", "cuesta", "costo", "pago", "compra")):
                    role = "costo"
            if role:
                amb = data.pop("ambiguous_cents")
                data["price_cents" if role == "precio" else "cost_cents"] = amb
                changed = True
        elif miss == "counterparty":
            clean = raw.strip(" .,!¿?").strip()
            name = clean.title() if 0 < len(clean.split()) <= 3 and not any(ch.isdigit() for ch in clean) else f.get("counterparty")
            if not name:
                words = [w for w in nlu.normalize(raw).split() if w not in nlu.NAME_STOP and not w.isdigit()]
                name = words[0].capitalize() if words else None
            if nlu.normalize(raw) in ("nadie", "no se", "no importa", "ninguno", "sin nombre", "cliente"):
                name = "Sin nombre"
            if name:
                data["counterparty"] = name
                changed = True
        elif miss == "parent":
            name = f.get("counterparty")
            if f.get("option_index") and d.options and 1 <= f["option_index"] <= len(d.options):
                data["parent_id"] = d.options[f["option_index"] - 1]["id"]
                changed = True
            elif d.options:
                t = nlu.normalize(raw)
                for opt in d.options:
                    if nlu.normalize(opt["name"]).split()[0] in t.split() or (name and name.lower() == opt["name"].lower()):
                        data["parent_id"] = opt["id"]
                        changed = True
                        break
        elif miss == "goal" and d.options:
            t = nlu.normalize(raw)
            for i, opt in enumerate(d.options, 1):
                if f.get("option_index") == i or any(w in t.split() for w in nlu.normalize(opt["name"]).split() if len(w) > 3):
                    data["goal_id"] = opt["id"]
                    changed = True
                    break
        elif miss == "amount_choice":
            amt = f.get("amount_cents") or f.get("total_cents") or f.get("bare_number")
            if f.get("option_index") and d.options and 1 <= f["option_index"] <= len(d.options):
                amt = d.options[f["option_index"] - 1]["cents"]
            if amt:
                data.pop("amount_options", None)
                data["total_cents"] = amt
                changed = True
        if miss == "method" and data.get("kind") == M.SALE and f.get("fully_credit"):
            data["paid_cents"] = 0
            data["method"] = None
            changed = True
        # valores generales (correcciones del borrador: «no, eran dos», «fue por Yape», «50»)
        for key in ("method", "quantity", "counterparty", "paid_cents", "pending_cents"):
            if key in f and f[key] is not None and data.get(key) != f[key]:
                if key == "counterparty" and miss not in ("counterparty", None) and data.get("counterparty"):
                    continue
                data[key] = f[key]
                changed = True
        if f.get("product_candidates") and miss != "product" and d.action in ("movimiento", "catalogo", "conteo"):
            if data.get("product_candidates") != f["product_candidates"]:
                data["product_candidates"] = f["product_candidates"]
                data.pop("product_id", None)
                changed = True
        amount = f.get("total_cents") or f.get("amount_cents") or f.get("bare_number")
        if amount and miss not in ("price_role", "amount_choice", "catalog_role"):
            if d.action == "movimiento":
                if data.get("kind") in (M.SALE, M.PURCHASE):
                    if f.get("price_role") == "unidad":
                        data["unit_price_cents"] = amount
                        data.pop("total_cents", None)
                    elif not (miss == "quantity" and "quantity" in f):
                        data["total_cents"] = amount
                        data.pop("unit_price_cents", None)
                        data.pop("ambiguous_price_cents", None)
                else:
                    data["amount_cents"] = amount
                changed = True
            elif d.action == "meta":
                data["target_cents"] = amount
                changed = True
            elif d.action == "catalogo" and miss == "catalog_value":
                data["ambiguous_cents"] = amount
                changed = True
        if miss == "quantity" and f.get("bare_number") and "quantity" not in f:
            data["quantity"] = f["bare_number"] // 100
            data.pop("total_cents", None) if data.get("total_cents") == f["bare_number"] else None
            changed = True
        if miss == "name" and d.action == "meta":
            data["name"] = cap(raw.strip())
            changed = True
        if miss == "stock_qty" and (f.get("quantity") or f.get("bare_number")):
            data["counted"] = f.get("quantity") or f["bare_number"] // 100
            changed = True
        if changed:
            d.data = data
            self.db.flush()
        return changed

    def ask(self, d: M.Draft, field: str, question: str, quick: list[str] | None = None,
            options: list | None = None, summary_read: bool = False) -> dict[str, Any]:
        d.missing = field
        d.options = options
        d.summary_read = summary_read
        self.db.commit()
        return self.resp(question, d, quick)

    def step(self, d: M.Draft, reask: bool = False, auto_confirm: bool = False) -> dict[str, Any]:
        handler = {"movimiento": self.step_movement, "catalogo": self.step_catalog, "saldo": self.step_balance,
                   "conteo": self.step_count, "meta": self.step_goal, "correccion": self.step_correction,
                   "anulacion": lambda d, **k: self.resp("¿Lo anulo?", d, ["Sí", "No"])}[d.action]
        r = handler(d, auto_confirm=auto_confirm)
        if reask and r.get("reply"):
            r["reply"] = "No te entendí. " + r["reply"]
        return r

    # ------------------------------------------------------------ movimientos
    def _product(self, data: dict[str, Any]) -> M.Product | None:
        if data.get("product_id"):
            return self.db.get(M.Product, data["product_id"])
        c = data.get("product_candidates") or []
        if len(c) == 1:
            data["product_id"] = c[0]
            return self.db.get(M.Product, c[0])
        return None

    def step_movement(self, d: M.Draft, auto_confirm: bool = False) -> dict[str, Any]:
        data = dict(d.data)
        k = data["kind"]
        product = None
        if k in (M.SALE, M.PURCHASE, M.STOCK_ADJ):
            cands = data.get("product_candidates") or []
            if len(cands) > 1 and not data.get("product_id"):
                opts = [{"id": p.id, "name": p.name} for p in (self.db.get(M.Product, c) for c in cands)]
                names = " o ".join(o["name"].lower() for o in opts)
                d.data = data
                return self.ask(d, "product", f"¿Cuál fue: {names}?", [o["name"] for o in opts], opts)
            product = self._product(data)
            if product is None and data.get("new_product"):
                data["new_product_name"] = cap(data["new_product"])
            if k == M.STOCK_ADJ and product is None:
                d.data = data
                return self.ask(d, "product", "¿De qué producto?",
                                [p.name for p in self.products()[:4]], [{"id": p.id, "name": p.name} for p in self.products()])

        if k in (M.SALE, M.PURCHASE):
            qty = data.get("quantity")
            ref_unit = (product.price_cents if k == M.SALE else product.cost_cents) if product else None
            if data.get("amount_options") and len(set(data["amount_options"])) > 1 and not data.get("total_cents_confirmed"):
                opts = [{"cents": c} for c in data["amount_options"]]
                d.data = data
                return self.ask(d, "amount_choice",
                                f"Escuché dos montos: {' y '.join(soles(c) for c in data['amount_options'])}. ¿Cuál fue el total?",
                                [soles(c) for c in data["amount_options"]], opts)
            if data.get("ambiguous_price_cents") is not None:
                amb = data["ambiguous_price_cents"]
                if not qty or qty == 1:
                    data["total_cents"] = data.pop("ambiguous_price_cents")
                elif ref_unit and abs(amb - ref_unit) <= 0.25 * ref_unit and abs(amb - ref_unit * qty) > 0.25 * ref_unit * qty:
                    data["unit_price_cents"] = data.pop("ambiguous_price_cents")
                else:
                    d.data = data
                    return self.ask(d, "price_role", f"¿{soles(amb)} es el total o el precio de cada uno?",
                                    ["Es el total", "Cada uno"])
            if data.get("unit_price_cents") is not None and qty:
                data["total_cents"] = data.pop("unit_price_cents") * qty
            if data.get("total_cents") is None:
                if data.get("paid_cents") is not None and data.get("pending_cents") is not None:
                    data["total_cents"] = data["paid_cents"] + data["pending_cents"]
                elif k == M.SALE and data.get("fully_credit") and data.get("pending_cents"):
                    data["total_cents"] = data["pending_cents"]
                else:
                    d.data = data
                    hint = []
                    if ref_unit and qty:
                        hint = [soles(ref_unit * qty)]
                    return self.ask(d, "amount", "¿Por cuánto en total?" if k == M.SALE else "¿Cuánto pagaste en total?", hint)
            if k == M.PURCHASE and not qty and product and product.track_stock and not data.get("generic"):
                d.data = data
                return self.ask(d, "quantity", f"¿Cuántas unidades de {product.name.lower()} compraste?")
            if k == M.PURCHASE and (data.get("generic") or not product):
                data["units_pending"] = True
            total = data["total_cents"]
            # pagos parciales y fiados
            if k == M.SALE:
                if data.get("fully_credit") and data.get("paid_cents") is None:
                    data["paid_cents"] = 0
                if data.get("pending_cents") is not None and data.get("paid_cents") is None:
                    data["paid_cents"] = max(0, total - data["pending_cents"])
                paid = data.get("paid_cents", total)
                if paid > total:
                    data["paid_cents"] = total
                    paid = total
                if paid < total and not data.get("counterparty"):
                    d.data = data
                    return self.ask(d, "counterparty", "¿Quién te quedó debiendo?")
            else:
                paid = total
            if paid > 0 and data.get("method") not in M.POCKETS:
                d.data = data
                summary = self.summary_text(data, product, with_question=False)
                q = "¿En efectivo o por Yape?" if data.get("method") != "mixto" else \
                    "¿Fue en efectivo o por Yape? Si fue parte y parte, dímelo como dos registros."
                return self.ask(d, "method", f"{summary} {q}", ["Efectivo", "Yape"], summary_read=True)
        elif k == M.TRANSFER:
            if not data.get("amount_cents"):
                d.data = data
                return self.ask(d, "amount", "¿Cuánto pasaste?")
        elif k == M.STOCK_ADJ:
            if data.get("amount_cents") and data.get("method") not in M.POCKETS:
                d.data = data
                return self.ask(d, "method", "¿Devolviste la plata en efectivo o por Yape?", ["Efectivo", "Yape"])
        else:
            amount = data.get("amount_cents") or data.get("total_cents") or data.get("paid_cents") or data.get("bare_number")
            if k == M.COLLECTION:
                r = self._resolve_parent(d, data)
                if r:
                    return r
                if not amount:
                    sale = self.db.get(M.Movement, data["parent_id"])
                    pend = ledger.sale_pending(self.db, sale)
                    d.data = data
                    return self.ask(d, "amount", f"¿Cuánto te pagó? Te debía {soles(pend)}.", [soles(pend)])
            if k == M.DEBT_PAYMENT:
                debts = self.db.scalars(select(M.Debt).where(M.Debt.business_id == self.b.id, M.Debt.active.is_(True))).all()
                if len(debts) == 1:
                    data["debt_id"] = debts[0].id
                    data["counterparty"] = data.get("counterparty") or debts[0].creditor
                    amount = amount or debts[0].installment_cents
            if k == M.GOAL_SAVING:
                r = self._resolve_goal(d, data)
                if r:
                    return r
            if not amount:
                d.data = data
                return self.ask(d, "amount", "¿De cuánto fue?")
            data["amount_cents"] = amount
            if data.get("method") not in M.POCKETS:
                d.data = data
                summary = self.summary_text(data, product, with_question=False)
                verb = "¿Salió del efectivo o del Yape?" if k in (M.EXPENSE, M.WITHDRAWAL, M.DEBT_PAYMENT, M.GOAL_SAVING) \
                    else "¿Entró en efectivo o por Yape?"
                return self.ask(d, "method", f"{summary} {verb}", ["Efectivo", "Yape"], summary_read=True)
        d.data = data
        if auto_confirm:
            return self.confirm(d)
        d.missing = None
        d.options = None
        d.summary_read = True
        self.db.commit()
        return self.resp(self.summary_text(data, product), d, ["Sí, guardar", "Corregir", "Cancelar"])

    def _resolve_parent(self, d: M.Draft, data: dict[str, Any]) -> dict[str, Any] | None:
        if data.get("parent_id"):
            return None
        rec = ledger.receivables(self.db, self.b.id)
        if not rec:
            d.data = data
            d.status = "cancelado"
            self.db.commit()
            return self.resp("No tengo fiados pendientes registrados. Si fue una venta nueva, dime «vendí...».")
        who = (data.get("counterparty") or "").lower()
        mine = [r for r in rec if r["counterparty"].lower() == who] if who else []
        if mine:
            data["parent_id"] = mine[0]["sale_id"]
            data["counterparty"] = mine[0]["counterparty"]
            return None
        if len(rec) == 1:
            data["parent_id"] = rec[0]["sale_id"]
            data["counterparty"] = rec[0]["counterparty"]
            return None
        opts = [{"id": r["sale_id"], "name": r["counterparty"]} for r in rec[:5]]
        d.data = data
        return self.ask(d, "parent", "¿Quién te pagó? " + ", ".join(f"{o['name']} ({soles(r['pending_cents'])})" for o, r in zip(opts, rec)),
                        [o["name"] for o in opts], opts)

    def _resolve_goal(self, d: M.Draft, data: dict[str, Any]) -> dict[str, Any] | None:
        if data.get("goal_id"):
            return None
        gs = self.db.scalars(select(M.Goal).where(M.Goal.business_id == self.b.id, M.Goal.kind == "ahorro",
                                                  M.Goal.status == "activa")).all()
        if not gs:
            d.status = "cancelado"
            self.db.commit()
            return self.resp("Aún no tienes una meta de ahorro. Dime «quiero juntar 1500 para una congeladora».")
        hint = nlu.normalize(data.get("goal_hint") or "")
        for g in gs:
            if hint and any(w in hint.split() for w in nlu.normalize(g.name).split() if len(w) > 3):
                data["goal_id"] = g.id
                return None
        if len(gs) == 1:
            data["goal_id"] = gs[0].id
            return None
        opts = [{"id": g.id, "name": g.name} for g in gs]
        d.data = data
        return self.ask(d, "goal", "¿Para cuál meta? " + " o ".join(o["name"] for o in opts), [o["name"] for o in opts], opts)

    def summary_text(self, data: dict[str, Any], product: M.Product | None, with_question: bool = True) -> str:
        k = data["kind"]
        q = " ¿Lo guardo?" if with_question else ""
        name = product.name if product else data.get("new_product_name") or ("mercadería" if k == M.PURCHASE else "venta")
        if k == M.SALE:
            total = data["total_cents"]
            qty = data.get("quantity")
            what = qty_name(qty, name) if (product or data.get("new_product_name")) else "Venta"
            s = f"{cap(what)}, {soles(total)}"
            paid = data.get("paid_cents", total)
            if data.get("method") in M.POCKETS and paid:
                s += f" {method_txt(data['method'])}"
            if product and product.price_cents and qty:
                disc = max(0, product.price_cents * qty - total)
                if disc:
                    s += f", con {soles(disc)} de descuento"
            if paid < total:
                s += f". Te pagó {soles(paid)} y te debe {soles(total - paid)}" + (f" ({data['counterparty']})" if data.get("counterparty") else "")
            if data.get("new_product_name") and not product:
                s += ". Es un producto nuevo, lo agrego a tu catálogo"
            return s + "." + q
        if k == M.PURCHASE:
            qty = data.get("quantity")
            total = data["total_cents"]
            if qty and (product or data.get("new_product_name")):
                s = f"Compra de {qty_name(qty, name)} por {soles(total)}{_m(data.get('method'))}, a {soles(round(total / qty))} cada uno"
            else:
                s = f"Compra de mercadería por {soles(total)}{_m(data.get('method'))}. Las unidades quedan pendientes"
            return s.strip() + "." + q
        amt = data.get("amount_cents")
        if k == M.EXPENSE:
            return f"Gasto del negocio: {data.get('category', 'gasto').lower()}, {soles(amt)}{_m(data.get('method'))}.{q}"
        if k == M.WITHDRAWAL:
            return f"Retiro para la casa ({data.get('description', 'casa')}): {soles(amt)}{_m(data.get('method'))}. No cuenta como gasto del negocio.{q}"
        if k == M.CONTRIBUTION:
            return f"Aporte de tu plata al negocio: {soles(amt)}{_m(data.get('method'))}. No cuenta como venta.{q}"
        if k == M.TRANSFER:
            return f"Paso {soles(amt)} de {data['method']} a {data['to_method']}. No cambia tus ventas.{q}"
        if k == M.COLLECTION:
            return f"{data.get('counterparty', 'Tu cliente')} te pagó {soles(amt)} del fiado{_m(data.get('method'))}.{q}"
        if k == M.DEBT_PAYMENT:
            return f"Pago de cuota{(' a ' + data['counterparty']) if data.get('counterparty') else ''}: {soles(amt)}{_m(data.get('method'))}.{q}"
        if k == M.GOAL_SAVING:
            g = self.db.get(M.Goal, data["goal_id"]) if data.get("goal_id") else None
            return f"Separas {soles(amt)} {('del ' + data['method']) if data.get('method') else ''} para «{g.name if g else 'tu meta'}».{q}"
        if k == M.STOCK_ADJ:
            label = {"merma": "Merma", "devolucion": "Devolución", "ajuste": "Ajuste"}[data.get("reason", "ajuste")]
            return f"{label}: {qty_name(data.get('quantity'), name)}.{q}"
        return "¿Lo guardo?"

    # ------------------------------------------------------------ confirmación
    def confirm(self, d: M.Draft) -> dict[str, Any]:
        if d.status == "confirmado":
            return self.resp("Eso ya está guardado.", duplicate=True)
        if d.missing and d.action != "anulacion":
            r = self.step(d)
            if d.missing:
                return r
        handler = {"movimiento": self.confirm_movement, "catalogo": self.confirm_catalog, "saldo": self.confirm_balance,
                   "meta": self.confirm_goal, "correccion": self.confirm_correction, "anulacion": self.confirm_void,
                   "consentimiento": lambda d: self.consent(True, d), "conteo": lambda d: self.step_count(d)}[d.action]
        return handler(d)

    def confirm_movement(self, d: M.Draft) -> dict[str, Any]:
        data = dict(d.data)
        product = self._product(data)
        if product is None and data.get("new_product_name") and data["kind"] in (M.SALE, M.PURCHASE):
            nm = data["new_product_name"]
            product = M.Product(business_id=self.b.id, name=nm, aliases=[nlu.normalize(nm), nlu.normalize(nm) + "s"],
                                track_stock=self.b.kind == "reventa", is_service=self.b.kind == "servicios")
            if data["kind"] == M.SALE and data.get("quantity"):
                product.price_cents = round(data["total_cents"] / data["quantity"])
            self.db.add(product)
            self.db.flush()
            data["product_id"] = product.id
        payload = {k: v for k, v in data.items() if k in {
            "kind", "occurred_at", "method", "to_method", "product_id", "quantity", "category", "expense_type",
            "counterparty", "description", "raw_text", "parent_id", "goal_id", "debt_id", "units_pending", "reason",
            "paid_cents", "generic"}}
        payload["amount_cents"] = data.get("total_cents") if data["kind"] in (M.SALE, M.PURCHASE) else data.get("amount_cents")
        if data["kind"] == M.PURCHASE and data.get("quantity") and not product:
            payload["units_pending"] = True
        try:
            mv, created = ledger.record(self.db, self.b, payload, op_id=d.op_id, channel=self.channel, commit=False)
        except ledger.LedgerError as e:
            self.db.rollback()
            return self.resp(f"No pude guardarlo: {e}.")
        d.status = "confirmado"
        self.db.commit()
        return self.resp(self.after_confirm(mv), movement=mv, quick=["Resumen de hoy", "Deshacer"] if created else [])

    def after_confirm(self, mv: M.Movement) -> str:
        db = self.db
        cash = metrics.cash_position(db, self.b)
        parts = ["Listo, guardado."]
        if mv.kind == M.SALE and mv.product:
            p = mv.product
            if mv.unit_cost_cents is not None and mv.quantity:
                parts.append(f"Ganaste aprox. {soles(mv.amount_cents - mv.unit_cost_cents * mv.quantity)}.")
            elif not p.is_service:
                parts.append("Margen pendiente: dime cuánto te cuesta comprarlo.")
            if p.track_stock:
                exp = ledger.expected_stock(db, p)
                if exp is None:
                    parts.append(f"Aún no sé cuántos {pluralize(p.name.lower())} tenías; dime «tengo 10 {pluralize(p.name.lower())}».")
                elif exp < 0:
                    parts.append(f"Ojo: el stock de {pluralize(p.name.lower())} da negativo ({exp}). Revisa tu stock inicial o compras.")
                else:
                    parts.append(f"Te quedan {exp}.")
        if mv.kind == M.PURCHASE and mv.product and mv.product.track_stock and mv.quantity:
            exp = ledger.expected_stock(db, mv.product)
            if exp is not None:
                parts.append(f"Ahora tienes {exp} {pluralize(mv.product.name.lower())}.")
        if mv.kind == M.COLLECTION:
            parent = db.get(M.Movement, mv.parent_id)
            pend = ledger.sale_pending(db, parent)
            parts.append(f"Aún te debe {soles(pend)}." if pend else "Ya no te debe nada.")
        if mv.kind == M.GOAL_SAVING:
            g = db.get(M.Goal, mv.goal_id)
            gs = metrics.goal_status(db, self.b, g)
            parts.append(f"Vas al {gs['progress_pct']}% de «{g.name}».")
        if mv.method in M.POCKETS and cash["known"].get(mv.method):
            pocket_bal = cash["efectivo_cents"] if mv.method == "efectivo" else cash["yape_cents"]
            parts.append(f"{'Efectivo' if mv.method == 'efectivo' else 'Yape'}: {soles(pocket_bal)}.")
        return " ".join(parts)

    # ------------------------------------------------------------ catálogo
    def step_catalog(self, d: M.Draft, auto_confirm: bool = False) -> dict[str, Any]:
        data = dict(d.data)
        cands = data.get("product_candidates") or []
        if len(cands) > 1 and not data.get("product_id"):
            opts = [{"id": p.id, "name": p.name} for p in (self.db.get(M.Product, c) for c in cands)]
            d.data = data
            return self.ask(d, "product", f"¿De cuál hablas: {' o '.join(o['name'].lower() for o in opts)}?",
                            [o["name"] for o in opts], opts)
        product = self._product(data)
        if not product and not data.get("new_product"):
            d.data = data
            return self.ask(d, "product", "¿De qué producto?", [p.name for p in self.products()[:4]],
                            [{"id": p.id, "name": p.name} for p in self.products()])
        if data.get("ambiguous_cents") is not None:
            d.data = data
            return self.ask(d, "catalog_role",
                            f"¿{soles(data['ambiguous_cents'])} es el precio al que lo vendes o lo que te cuesta comprarlo?",
                            ["Lo vendo a ese precio", "Me cuesta eso"])
        name = product.name if product else cap(data["new_product"])
        parts = []
        if data.get("price_cents") is not None:
            parts.append(f"precio de venta {soles(data['price_cents'])}")
        if data.get("cost_cents") is not None:
            parts.append(f"costo de compra {soles(data['cost_cents'])}")
        if data.get("stock") is not None:
            parts.append(f"{data['stock']} en stock")
        if not parts:
            d.data = data
            return self.ask(d, "catalog_value", f"¿Qué dato de {name.lower()} quieres guardar: precio, costo o stock?")
        d.data = data
        d.missing = None
        d.summary_read = True
        self.db.commit()
        return self.resp(f"{name}: {', '.join(parts)}. ¿Lo guardo?", d, ["Sí, guardar", "Cancelar"])

    def confirm_catalog(self, d: M.Draft) -> dict[str, Any]:
        data = d.data
        product = self._product(dict(data))
        if not product:
            nm = cap(data["new_product"])
            product = M.Product(business_id=self.b.id, name=nm, aliases=[nlu.normalize(nm)],
                                track_stock=self.b.kind == "reventa", is_service=self.b.kind == "servicios")
            self.db.add(product)
            self.db.flush()
        msg = []
        if data.get("price_cents") is not None:
            product.price_cents = data["price_cents"]
        if data.get("cost_cents") is not None:
            product.cost_cents = data["cost_cents"]
        if data.get("stock") is not None:
            if product.initial_stock is None:
                product.initial_stock = data["stock"] - ledger.stock_delta(self.db, product.id)
                msg.append(f"Desde ahora llevo la cuenta: {data['stock']} en stock.")
            else:
                c = reconcile.stock_count(self.db, self.b, product, data["stock"], commit=False)
                self.db.flush()
                msg.append(reconcile.count_text(self.db, c))
        d.status = "confirmado"
        self.db.commit()
        return self.resp(f"Listo, actualicé {product.name.lower()}. " + " ".join(msg))

    # ------------------------------------------------------------ saldo inicial
    def step_balance(self, d: M.Draft, auto_confirm: bool = False) -> dict[str, Any]:
        bal = d.data["balances"]
        txt = " y ".join(f"{soles(v)} en {'Yape' if k == 'yape' else 'efectivo'}" for k, v in bal.items())
        d.summary_read = True
        d.missing = None
        self.db.commit()
        return self.resp(f"Tu saldo inicial: {txt}. ¿Lo guardo?", d, ["Sí, guardar", "Cancelar"])

    def confirm_balance(self, d: M.Draft) -> dict[str, Any]:
        known = ledger.opening_known(self.db, self.b.id)
        for pocket, cents in d.data["balances"].items():
            if known.get(pocket):
                old = self.db.scalar(select(M.Movement).where(M.Movement.business_id == self.b.id, M.Movement.kind == M.OPENING,
                                                              M.Movement.method == pocket, M.Movement.status == "confirmado"))
                ledger.revise(self.db, self.b, old, {"amount_cents": cents}, reason="saldo inicial corregido", commit=False)
            else:
                first = self.db.scalar(select(M.Movement.occurred_at).where(M.Movement.business_id == self.b.id)
                                       .order_by(M.Movement.occurred_at))
                when = (first - timedelta(minutes=1)) if first else now_lima()
                ledger.record(self.db, self.b, {"kind": M.OPENING, "method": pocket, "amount_cents": cents,
                                                "occurred_at": when, "description": "Saldo inicial"},
                              op_id=f"{d.op_id}-{pocket}", channel=self.channel, commit=False)
        d.status = "confirmado"
        self.db.commit()
        return self.resp("Listo. " + summaries.cash_line(self.db, self.b))

    # ------------------------------------------------------------ conteo
    def step_count(self, d: M.Draft, auto_confirm: bool = False) -> dict[str, Any]:
        data = dict(d.data)
        cands = data.get("product_candidates") or []
        if len(cands) > 1 and not data.get("product_id"):
            opts = [{"id": p.id, "name": p.name} for p in (self.db.get(M.Product, c) for c in cands)]
            d.data = data
            return self.ask(d, "product", f"¿Cuál contaste: {' o '.join(o['name'].lower() for o in opts)}?",
                            [o["name"] for o in opts], opts)
        product = self._product(data)
        c = reconcile.stock_count(self.db, self.b, product, data["counted"], commit=False)
        d.status = "confirmado"
        self.db.commit()
        quick = ["Ajustar stock", "Dejar pendiente"] if c.result == "diferencia" else []
        return self.resp(reconcile.count_text(self.db, c), quick=quick, count=metrics._count_dict(c))

    # ------------------------------------------------------------ metas
    def step_goal(self, d: M.Draft, auto_confirm: bool = False) -> dict[str, Any]:
        data = dict(d.data)
        if not data.get("target_cents"):
            d.data = data
            return self.ask(d, "amount", "¿Cuánto necesitas juntar?")
        if not data.get("name"):
            data["name"] = "Reponer mercadería" if data.get("kind") == "reposicion" else "Mi meta"
        d.data = data
        txt = f"Meta «{data['name']}»: {soles(data['target_cents'])}"
        if data.get("deadline"):
            dl = date.fromisoformat(data["deadline"])
            days = max(1, (dl - self.today).days)
            txt += f" para el {dl.day}/{dl.month}. Tendrías que separar {soles(round(data['target_cents'] / days * 7))} por semana"
            st30 = metrics.period_stats(self.db, self.b, self.today - timedelta(days=30), self.today + timedelta(days=1))
            if st30["profit_cents"] > 0:
                share = round(100 * (data["target_cents"] / days * 30) / st30["profit_cents"])
                txt += f", el {share}% de lo que ganas al mes"
        elif data.get("kind") == "reposicion":
            cash = metrics.cash_position(self.db, self.b)
            if cash["available_for_restock_cents"] is not None:
                txt += f". Hoy tienes {soles(max(0, cash['available_for_restock_cents']))} disponibles"
        d.missing = None
        d.summary_read = True
        self.db.commit()
        return self.resp(txt + ". ¿La guardo?", d, ["Sí, guardar", "Cancelar"])

    def confirm_goal(self, d: M.Draft) -> dict[str, Any]:
        data = d.data
        g = M.Goal(business_id=self.b.id, kind=data.get("kind", "ahorro"), name=data["name"],
                   target_cents=data["target_cents"],
                   deadline=date.fromisoformat(data["deadline"]) if data.get("deadline") else None)
        self.db.add(g)
        d.status = "confirmado"
        self.db.commit()
        st = metrics.goal_status(self.db, self.b, g)
        return self.resp("Meta guardada. " + st["message"])

    # ------------------------------------------------------------ correcciones
    def last_movement(self) -> M.Movement | None:
        return self.db.scalar(select(M.Movement).where(M.Movement.business_id == self.b.id, M.Movement.status == "confirmado",
                                                       M.Movement.kind != M.OPENING).order_by(M.Movement.created_at.desc(), M.Movement.id.desc()))

    def start_correction(self, p: nlu.Parsed) -> dict[str, Any]:
        mv = self.last_movement()
        if not mv:
            return self.resp("No encontré un movimiento para corregir.")
        d = self.new_draft("correccion", {"movement_id": mv.id, "changes": self._changes(mv, p.fields)})
        return self.step(d)

    def _changes(self, mv: M.Movement, f: dict[str, Any]) -> dict[str, Any]:
        ch: dict[str, Any] = {}
        if f.get("method") in M.POCKETS:
            ch["method"] = f["method"]
        if f.get("quantity"):
            ch["quantity"] = f["quantity"]
        amount = f.get("total_cents") or f.get("amount_cents") or f.get("bare_number")
        if amount and amount != (f.get("quantity") or 0) * 100:
            ch["amount_cents"] = amount
        if f.get("product_candidates") and len(f["product_candidates"]) == 1 and f["product_candidates"][0] != mv.product_id:
            ch["product_id"] = f["product_candidates"][0]
        return ch

    def step_correction(self, d: M.Draft, auto_confirm: bool = False) -> dict[str, Any]:
        mv = self.db.get(M.Movement, d.data["movement_id"])
        ch = d.data.get("changes") or {}
        if not ch:
            return self.ask(d, "changes", f"¿Qué corrijo de tu {MOVEMENT_LABEL[mv.kind]} ({describe_movement(self.db, mv)})? "
                                          "Dime por ejemplo «eran dos», «fue por Yape» o «fue 45».")
        preview = dict(ledger.snapshot(mv))
        preview.update(ch)
        txt = f"Corrijo tu {MOVEMENT_LABEL[mv.kind]}: antes {describe_movement(self.db, mv)}; ahora {describe_snapshot(self.db, preview)}. ¿Lo guardo?"
        d.missing = None
        d.summary_read = True
        self.db.commit()
        return self.resp(txt, d, ["Sí, guardar", "Cancelar"])

    def confirm_correction(self, d: M.Draft) -> dict[str, Any]:
        mv = self.db.get(M.Movement, d.data["movement_id"])
        try:
            ledger.revise(self.db, self.b, mv, d.data["changes"], reason="corrección por chat", commit=False)
        except ledger.LedgerError as e:
            self.db.rollback()
            return self.resp(f"No pude corregirlo: {e}.")
        d.status = "confirmado"
        self.db.commit()
        return self.resp(f"Corregido. Quedó: {describe_movement(self.db, mv)}. Guardé el cambio en el historial.", movement=mv)

    def confirm_void(self, d: M.Draft) -> dict[str, Any]:
        mv = self.db.get(M.Movement, d.data["movement_id"])
        ledger.void(self.db, mv, reason="anulado por chat", commit=False)
        d.status = "confirmado"
        self.db.commit()
        return self.resp("Anulado. Revertí sus efectos en caja y stock y quedó en el historial.", movement=mv)

    # ------------------------------------------------------------ consentimiento mensual BCP
    def pending_consent_month(self) -> date | None:
        prev = add_months(month_start(self.today), -1)
        key = prev.strftime("%Y-%m")
        if self.db.scalar(select(M.ReportConsent).where(M.ReportConsent.business_id == self.b.id, M.ReportConsent.month == key)):
            return None
        has = self.db.scalar(select(M.Movement.id).where(M.Movement.business_id == self.b.id,
                                                         M.Movement.occurred_at >= datetime(prev.year, prev.month, 1),
                                                         M.Movement.occurred_at < datetime(self.today.year, self.today.month, 1)))
        return prev if has else None

    def with_consent_prompt(self, r: dict[str, Any]) -> dict[str, Any]:
        if r.get("draft"):
            return r
        prev = self.pending_consent_month()
        if not prev:
            return r
        already = self.db.scalar(select(M.Draft).where(M.Draft.business_id == self.b.id, M.Draft.action == "consentimiento",
                                                       M.Draft.conversation == self.conv))
        if already and already.data.get("month") == prev.strftime("%Y-%m"):
            return r
        d = self.new_draft("consentimiento", {"month": prev.strftime("%Y-%m")})
        d.summary_read = True
        self.db.commit()
        r["reply"] += f" Por cierto: ya está tu informe de {month_label(prev)}. ¿Quieres que se le envíe al BCP?"
        r["draft"] = self.draft_view(d)
        r["quick_replies"] = ["Sí, envíalo", "No por ahora"]
        return r

    def consent(self, yes: bool, d: M.Draft | None = None) -> dict[str, Any]:
        prev = add_months(month_start(self.today), -1)
        key = d.data["month"] if d else prev.strftime("%Y-%m")
        existing = self.db.scalar(select(M.ReportConsent).where(M.ReportConsent.business_id == self.b.id, M.ReportConsent.month == key))
        if not existing:
            self.db.add(M.ReportConsent(business_id=self.b.id, month=key, decision="si" if yes else "no"))
        if d:
            d.status = "confirmado"
        self.db.commit()
        self.db.commit()
        if yes:
            return self.resp("Listo, autorizaste el envío de tu informe al BCP. En esta demo el envío es simulado: "
                             "puedes revisarlo y descargarlo en «Reporte».")
        return self.resp("Ok, no lo envío. Lo tienes en «Reporte» cuando lo necesites.")

    # ------------------------------------------------------------ onboarding por chat
    def onboarding(self, text: str) -> dict[str, Any]:
        t = nlu.normalize(text)
        if self.b.setup_state == "pendiente":
            if len(t.split()) < 3:
                return self.resp("¡Hola! Soy tu asistente de números. Cuéntame qué vendes y cómo te pagan.",
                                 quick=["Vendo polos y cobro por Yape y efectivo", "Vendo menú", "Hago cortes de cabello"])
            p = setup.propose(self.db, self.b, text)
            return self.resp(setup.proposal_text(p), quick=["Sí, guardar", "Usar plantilla de reventa", "Usar plantilla de comida", "Usar plantilla de servicios"],
                             setup=p)
        # propuesta en espera
        if nlu.CONFIRM_RE.match(t):
            setup.apply(self.db, self.b)
            return self.resp("¡Listo, tu negocio está configurado! Ya puedes dictarme tus ventas. "
                             "Si quieres, dime tu saldo inicial: «empiezo con 200 en efectivo y 100 en Yape».")
        for kind in ("reventa", "comida", "servicios"):
            if kind in t:
                setup.from_template(self.db, self.b, kind)
                return self.resp(f"Listo, usé la plantilla de {kind}. Ya puedes dictarme tus ventas.")
        if nlu.CANCEL_RE.match(t) and len(t.split()) <= 3:
            self.b.setup_state = "pendiente"
            self.db.commit()
            return self.resp("Ok, cuéntame de nuevo qué vendes y cómo te pagan.")
        p = setup.propose(self.db, self.b, text)
        return self.resp(setup.proposal_text(p), quick=["Sí, guardar", "Usar plantilla de reventa"], setup=p)


# ------------------------------------------------------------------ vistas

def describe_snapshot(db: Session, s: dict[str, Any]) -> str:
    p = db.get(M.Product, s["product_id"]) if s.get("product_id") else None
    k = s["kind"]
    amt = soles(s["amount_cents"])
    if k in (M.SALE, M.PURCHASE) and p:
        return f"{qty_name(s.get('quantity'), p.name)}, {amt}{_m(s.get('method'))}"
    return f"{amt}{_m(s.get('method'))}"


def describe_movement(db: Session, mv: M.Movement) -> str:
    return describe_snapshot(db, ledger.snapshot(mv))


def movement_view(db: Session, mv: M.Movement) -> dict[str, Any]:
    from .report import CHECK_LABEL, ORIGIN_LABEL
    return {
        "id": mv.id, "op_id": mv.op_id, "kind": mv.kind, "label": MOVEMENT_LABEL.get(mv.kind, mv.kind),
        "occurred_at": mv.occurred_at.isoformat(), "amount_cents": mv.amount_cents, "paid_cents": mv.paid_cents,
        "pending_cents": ledger.sale_pending(db, mv) if mv.kind == M.SALE else 0,
        "method": mv.method, "to_method": mv.to_method, "product_id": mv.product_id,
        "product": mv.product.name if mv.product else None, "quantity": mv.quantity,
        "unit_price_ref_cents": mv.unit_price_ref_cents, "reference_total_cents": mv.reference_total_cents,
        "discount_cents": mv.discount_cents, "unit_cost_cents": mv.unit_cost_cents,
        "margin_cents": (mv.amount_cents - mv.unit_cost_cents * mv.quantity) if mv.kind == M.SALE and mv.unit_cost_cents is not None and mv.quantity else None,
        "units_pending": mv.units_pending, "category": mv.category, "expense_type": mv.expense_type,
        "counterparty": mv.counterparty, "description": mv.description, "raw_text": mv.raw_text,
        "channel": mv.channel, "origin": mv.origin, "origin_label": ORIGIN_LABEL.get(mv.origin, mv.origin),
        "check": reconcile.sale_check(db, mv) if mv.kind in (M.SALE, M.PURCHASE) else None,
        "check_label": CHECK_LABEL[reconcile.sale_check(db, mv)] if mv.kind in (M.SALE, M.PURCHASE) else None,
        "status": mv.status, "revision": mv.revision, "demo": mv.demo, "parent_id": mv.parent_id,
        "attachments": [{"id": a.id, "kind": a.kind, "filename": a.filename, "demo": a.demo} for a in mv.attachments],
    }


def process_message(db: Session, business: M.Business, text: str, *, message_id: str, channel: str = "web",
                    conversation: str | None = None, op_id: str | None = None, occurred_at: datetime | None = None,
                    via_voice: bool = False, transcript: str | None = None) -> dict[str, Any]:
    """Punto de entrada idempotente: el mismo message_id nunca se procesa dos veces."""
    prev = db.scalar(select(M.ProcessedMessage).where(M.ProcessedMessage.message_id == message_id))
    if prev:
        r = dict(prev.response)
        r["duplicate"] = True
        return r
    eng = Engine(db, business, conversation or f"{channel}:{business.id}", channel)
    db.add(M.ChatLog(business_id=business.id, role="user", text=text, channel=channel, via_voice=via_voice))
    r = eng.handle(text, op_id=op_id, occurred_at=occurred_at)
    if transcript is not None:
        r["transcript"] = transcript
    r["message_id"] = message_id
    db.add(M.ChatLog(business_id=business.id, role="bot", text=r["reply"], channel=channel))
    db.add(M.ProcessedMessage(message_id=message_id, business_id=business.id, channel=channel, text=text,
                              response=_jsonable(r)))
    db.commit()
    return r


def _jsonable(o):
    import json
    return json.loads(json.dumps(o, default=str))
