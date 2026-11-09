"""Primera conversación: conocer el negocio y armar su inventario sin que suene a «inventario».

Funciona igual por WhatsApp o por el chat de la app. El estado vive en Business.setup_proposal
(un documento JSON) y cada producto termina como una ficha JSON flexible en Product.spec.
Mientras la conversación no termine, no se registran ventas ni gastos.

Preguntas (una por turno):
  nombre → qué vende → ¿algo más? → cómo vende (kilo, unidad, atado, de a sol) → precio y costo de cada cosa
  → cómo compra (jaba de 20 kg, saco, docena…) → cuánto le queda → cómo le pagan → cuánta plata tiene → resumen
"""
from __future__ import annotations

import re
from datetime import timedelta
from typing import Any

from sqlalchemy import select

from . import ledger, nlu, units
from . import models as M
from .money import soles
from .templates import TEMPLATES, VEG, guess_kind
from .timeutil import now_lima

STAGES = ["nombre", "vende", "mas", "como", "precio", "compra", "stock", "pago", "gastos", "plata", "resumen"]
GENERIC = {"vendo", "vendemos", "venta", "ventas", "verdura", "verduras", "fruta", "frutas", "producto", "productos", "cosa",
           "cosas", "todo", "tipo", "mercado", "puesto", "tienda", "bodega", "tambien", "mas", "como", "varias", "varios",
           "otras", "otros", "hortalizas", "abarrotes", "mi", "negocio", "soy", "tengo", "un", "una", "1", "y", "e", "o",
           "de", "del", "la", "el", "los", "las", "en", "con", "para", "por", "que", "es", "son", "basicamente", "principalmente",
           "sobre", "nada", "eso", "algo", "kilo", "kilos", "atado", "atados", "soles", "sol", "jaba", "saco", "bueno", "pues",
           "ya", "si", "no", "aca", "aqui", "frescas", "frescos", "variedad", "diario", "mayormente", "puro", "pura",
           "al", "mediodia", "manana", "tarde", "noche", "dia", "dias", "casa", "calle", "mercado", "esquina"}
# Rubros: si la persona solo dice el rubro («vendo ropa»), se le pide qué cosas vende, con ejemplos de su rubro.
CATEGORIES = [
    (r"\b(ropa|prendas?|confecciones|vestidos|moda)\b", "prendas", "polos, blusas, pantalones, casacas"),
    (r"\b(comida|menu|menus|almuerzos?|desayunos?|platos?|cocina|restaurante|cevicheria|polleria)\b", "platos", "menú, caldo de gallina, ceviche"),
    (r"\b(abarrotes|bodega|tienda)\b", "productos", "arroz, azúcar, aceite, fideos"),
    (r"\b(frutas?|fruteria)\b", "frutas", "plátano, manzana, papaya, naranja"),
    (r"\b(verduras?|hortalizas|verduleria)\b", "verduras", "tomate, papa, cebolla, limón"),
    (r"\b(golosinas|dulces|snacks|confiteria)\b", "golosinas", "galletas, chocolates, caramelos"),
    (r"\b(accesorios|bisuteria|joyas|joyeria)\b", "accesorios", "aretes, collares, pulseras"),
    (r"\b(bebidas|jugos|refrescos)\b", "bebidas", "gaseosas, agua, jugos"),
    (r"\b(cosmeticos|maquillaje|belleza|perfumes)\b", "productos", "labiales, cremas, perfumes"),
    (r"\b(zapatos|calzado|zapatillas)\b", "modelos", "zapatillas, sandalias, botas"),
    (r"\b(pan|panaderia|pasteles|tortas|reposteria)\b", "productos", "pan francés, tortas, alfajores"),
    (r"\b(utiles|libreria|papeleria)\b", "productos", "cuadernos, lapiceros, folders"),
]
GENERIC |= {"ropa", "prendas", "prenda", "confecciones", "moda", "comida", "comidas", "menu", "menus", "golosinas", "dulces",
            "snacks", "accesorios", "bisuteria", "bebidas", "cosmeticos", "maquillaje", "calzado", "utiles", "libreria",
            "bebe", "bebes", "nino", "ninos", "nina", "ninas", "dama", "damas", "varon", "varones", "hombre", "mujer",
            "segunda", "mano", "nueva", "nuevo", "importada", "americana", "fruteria", "verduleria", "panaderia", "confiteria"}


def category_hint(t: str) -> tuple[str, str] | None:
    for pat, word, ex in CATEGORIES:
        if re.search(pat, t):
            return word, ex
    return None
UNIT_WORDS = [
    (r"\b(de a sol|de a 1 soles|montoncitos?|porcion(es)?|al ojo|en soles|por soles|de a soles)\b", "soles"),
    (r"\b(kilos?|kg|por kilo|el kilo)\b", "kg"),
    (r"\b(atados?|manojos?)\b", "atado"),
    (r"\b(unidad(es)?|cada uno|cada una|pieza|por uno|por una|suelto)\b", "unidad"),
    (r"\b(docenas?)\b", "docena"),
    (r"\b(platos?|menus?)\b", "plato"),
    (r"\b(jabas?)\b", "jaba"), (r"\b(sacos?)\b", "saco"), (r"\b(cajas?)\b", "caja"), (r"\b(bolsas?)\b", "bolsa"),
    (r"\b(paquetes?)\b", "paquete"),
]
PACKS = {"jaba", "saco", "caja", "bolsa", "paquete", "docena"}
DONE_RE = re.compile(r"^(no|nada|nada mas|eso es todo|es todo|solo eso|ya|listo|ninguno|nop|no gracias|eso nomas|eso no mas)\b")
DONT_KNOW_RE = re.compile(r"\b(no se|no lo se|ni idea|varia|depende|no recuerdo|no estoy segura?|despues|luego|saltar|paso)\b")
VEG_NAMES = {nlu.normalize(n): n for n, _a, _u in VEG}


def _units_in(t: str) -> list[str]:
    found = []
    for pat, u in UNIT_WORDS:
        m = re.search(pat, t)
        if m:
            found.append((m.start(), u))
    return [u for _, u in sorted(found)]


def _money(t: str) -> list[int]:
    """Montos en el orden en que se dijeron (con o sin «soles»)."""
    out = []
    for m in re.finditer(r"(?:s/ ?)?(\d+(?:\.\d{1,2})?)(?:\s*(soles|sol|kilos?|kg|unidades|atados?))?", t):
        if m.group(2) and not m.group(2).startswith("sol"):
            continue   # «20 kilos» no es plata
        out.append(int(round(float(m.group(1)) * 100)))
    return out


def segments(raw: str) -> list[str]:
    """Parte el texto original por comas, «y», «e», «con» y luego normaliza cada parte."""
    parts = re.split(r"[,;:/\n]|\s+y\s+|\s+e\s+|\s+con\s+|\s+pero\s+", (raw or "").lower())
    return [nlu.normalize(x) for x in parts if x.strip()]


def _veg(word: str) -> str | None:
    return VEG_NAMES.get(word) or VEG_NAMES.get(nlu.singular(word))


def extract_names(text: str) -> list[str]:
    names: list[str] = []

    def add(n: str):
        if n and n.lower() not in [x.lower() for x in names]:
            names.append(n)
    for ch in segments(text):
        ch = re.sub(r"^(yo )?(vendo|vendemos|tengo|ofrezco|hago|preparo|me dedico a vender|me dedico a|tambien vendo|tambien)\b", "", ch).strip()
        words = [w for w in ch.split() if w not in GENERIC and not re.match(r"^\d", w) and len(w) > 2]
        if not words:
            continue
        known = [_veg(w) for w in words]
        if len(words) > 1 and sum(1 for k in known if k) >= 2:
            for w, k in zip(words, known):    # «tomate papa cebolla» dicho sin comas
                add(k or nlu.singular(w).capitalize())
            continue
        first = nlu.singular(words[0]) if not _veg(words[0]) else words[0]
        name = " ".join([first] + words[1:2])
        add(_veg(first) if (_veg(first) and len(words) == 1) else (VEG_NAMES.get(name) or name.capitalize()))
    return names[:25]


ACCENTS = {"platano": "plátano", "menu": "menú", "cafe": "café", "azucar": "azúcar", "maiz": "maíz", "aji": "ají",
           "pure": "puré", "brocoli": "brócoli", "rabano": "rábano", "esparrago": "espárrago", "cupcake": "cupcake"}


def _accent(name: str) -> str:
    """Devuelve la tilde que se pierde al normalizar: «pantalon» → «pantalón», «limon» → «limón»."""
    out = []
    for w in name.split():
        lw = w.lower()
        if lw in ACCENTS:
            fixed = ACCENTS[lw]
        elif len(lw) > 4 and lw.endswith("on") and not lw.endswith(("ion", "gon")):
            fixed = lw[:-2] + "ón"
        elif len(lw) > 4 and lw.endswith("ion"):
            fixed = lw[:-3] + "ión"
        else:
            fixed = lw
        out.append(fixed[:1].upper() + fixed[1:] if w[:1].isupper() else fixed)
    return " ".join(out)


def _product(name: str) -> dict[str, Any]:
    from .textutil import pluralize
    name = _accent(name)
    n = nlu.normalize(name)
    return {"name": name, "aliases": sorted({n, n + "s", nlu.singular(n), nlu.normalize(pluralize(name))}),
            "vende_por": [], "compra_por": {}, "base": None}


def _find(doc: dict[str, Any], t: str) -> list[int]:
    """Índices de productos mencionados en el texto."""
    refs = [nlu.ProductRef(i, p["name"], p["aliases"]) for i, p in enumerate(doc["products"])]
    out = []
    for r in refs:
        for term in nlu.product_terms(r):
            if re.search(rf"\b{re.escape(term)}\b", t):
                out.append(r.id)
                break
    return out


class Onboarding:
    def __init__(self, eng):
        self.eng = eng
        self.db = eng.db
        self.b: M.Business = eng.b
        doc = self.b.setup_proposal if (self.b.setup_proposal or {}).get("v") == 2 else None
        import copy
        self.doc: dict[str, Any] = copy.deepcopy(doc) if doc else {"v": 2, "stage": None, "products": [], "i": 0, "pending": None}

    # ------------------------------------------------------------ utilidades
    def save(self):
        import json
        from sqlalchemy.orm.attributes import flag_modified
        self.b.setup_proposal = json.loads(json.dumps(self.doc))   # copia nueva: el JSON siempre se guarda completo
        flag_modified(self.b, "setup_proposal")
        self.db.commit()

    def reply(self, text: str, quick: list[str] | None = None, done: bool = False) -> dict[str, Any]:
        self.save()
        stage = self.doc.get("stage") or "nombre"
        step = STAGES.index(stage) + 1 if stage in STAGES else len(STAGES)
        return self.eng.resp(text, quick=quick, setup={"stage": stage, "step": min(step, len(STAGES)), "total": len(STAGES),
                                                       "done": done, "products": self.doc["products"]})

    def unit_txt(self, p: dict[str, Any]) -> str:
        u = p.get("base") or self.doc.get("default_unit") or "unidad"
        return {"kg": "kilo", "unidad": "unidad", "atado": "atado", "docena": "docena", "plato": "plato"}.get(u, u)

    # ------------------------------------------------------------ preguntas
    def ask(self, stage: str, prefix: str = "") -> dict[str, Any]:
        self.doc["stage"] = stage
        d = self.doc
        owner = d.get("owner") or ""
        if stage == "nombre":
            return self.reply(prefix + "¡Hola! Soy Kallpa 👋 Te ayudo a llevar las cuentas de tu negocio con mensajes de voz, sin cuadernos. "
                                       "Primero quiero conocerte un poquito. ¿Cómo te llamas?")
        if stage == "vende":
            return self.reply(prefix + f"Mucho gusto{', ' + owner if owner else ''}. ¿Qué vendes? Cuéntamelo como a una amiga, "
                                       "por ejemplo «verduras: tomate, papa, cebolla y limón».")
        if stage == "mas":
            names = ", ".join(p["name"].lower() for p in d["products"])
            return self.reply(prefix + f"Anoté: {names}. ¿Vendes algo más? Dime qué, o «eso es todo».", ["Eso es todo"])
        if stage == "como":
            if d.get("kind") == "verduras":
                q = "¿Cómo vendes casi todo: por kilo, por unidad, por atado o de a sol (en montoncitos)? Si algo es distinto, dímelo, por ejemplo «por kilo, pero el culantro por atado»."
                return self.reply(prefix + q, ["Por kilo", "De a sol", "Por unidad"])
            if d.get("kind") == "comida":
                return self.reply(prefix + "¿Lo vendes por plato o por porción?", ["Por plato", "Por porción"])
            return self.reply(prefix + "¿Cómo lo vendes: por unidad, por kilo, por docena o por paquete?", ["Por unidad", "Por kilo", "Por docena"])
        if stage == "precio":
            p = d["products"][d["i"]]
            if d.get("pending") == "costo":
                return self.reply(prefix + f"¿Y a ti cuánto te cuesta el {self.unit_txt(p)} de {p['name'].lower()}? Si no sabes, di «no sé».", ["No sé"])
            if p.get("base") == "soles":
                return self.reply(prefix + f"El {p['name'].lower()} lo vendes de a sol. ¿De cuánto son tus montoncitos? Por ejemplo «de 1 y de 2 soles».", ["De 1 sol"])
            n = len(d["products"])
            pre = f"({d['i'] + 1} de {n}) " if n > 1 else ""
            return self.reply(prefix + pre + f"¿A cuánto das {'la' if self.unit_txt(p) in ('unidad', 'docena') else 'el'} {self.unit_txt(p)} de {p['name'].lower()}? ¿Y a ti cuánto te cuesta? "
                                             "Por ejemplo «a 4, me cuesta 2.50».", ["No sé"])
        if stage == "compra":
            pend = d.get("pending")
            if pend and pend.startswith("equiv:"):
                idx = int(pend.split(":")[1])
                p = d["products"][idx]
                return self.reply(prefix + f"¿Más o menos cuántos kilos trae la {p['compra_por']['unidad']} de {p['name'].lower()}?", ["No sé"])
            if d.get("kind") == "verduras":
                return self.reply(prefix + "¿Cómo compras en el mayorista? Por ejemplo «el tomate por jaba de 20 kilos a 50 soles, la papa por saco de 50 kilos». "
                                           "Si compras por kilo, dime «por kilo».", ["Por kilo", "No sé"])
            return self.reply(prefix + "¿Cómo compras tu mercadería? Por ejemplo «los polos por docena a 144» o «por unidad».", ["Por unidad", "No sé"])
        if stage == "stock":
            ex = "«2 jabas de tomate, medio saco de papa y 5 kilos de cebolla»" if d.get("kind") == "verduras" else "«10 polos y 5 shorts»"
            return self.reply(prefix + f"¿Cuánto te queda ahorita de cada cosa, más o menos? Por ejemplo {ex}. Si no sabes, di «no sé».", ["No sé"])
        if stage == "pago":
            return self.reply(prefix + "¿Cómo te pagan tus clientes: en efectivo, por Yape o de las dos formas?", ["Las dos", "Solo efectivo", "Solo Yape"])
        if stage == "gastos":
            from . import costs
            pend = d.get("pending") or ""
            if pend.startswith("gfreq:"):
                it = d["expenses"][int(pend.split(":")[1])]
                return self.reply(prefix + f"¿Cada cuánto pagas {it['name'].lower()} ({soles(it['amount_cents'])})?",
                                  ["Al día", "A la semana", "Al mes", "Al año"])
            if d.get("expenses"):
                return self.reply(prefix + "Anoté:\n" + "\n".join("• " + costs.line(i) for i in d["expenses"]) + "\n"
                                  + costs.totals_text(d["expenses"]) + "\n(" + costs.explain_types() + ")\n¿Pagas algo más? Dime qué y cada cuánto, o «eso es todo».",
                                  ["Eso es todo"])
            ex = ("«alquiler del puesto 250 al mes, luz 40 al mes, pasaje 10 al día, bolsas 15 a la semana, licencia 120 al año»"
                  if d.get("kind") != "comida" else
                  "«alquiler 500 al mes, gas 55 a la semana, ayudante 300 a la quincena, descartables 20 al día»")
            return self.reply(prefix + "Ahora tus gastos: ¿qué cosas pagas para tu negocio y cada cuánto? "
                              f"Por ejemplo {ex}. Si no pagas nada aparte de tu mercadería, di «nada».", ["Nada"])
        if stage == "plata":
            if d.get("pending") == "yape":
                return self.reply(prefix + "¿Y en tu Yape cuánto tienes? Lo ves al abrir tu app de Yape.", ["No sé"])
            return self.reply(prefix + "Última pregunta: cuenta la plata que tienes ahora en tu monedero. ¿Cuánto es?"
                              + (" Si también sabes cuánto tienes en Yape, dímelo." if "yape" in d.get("methods", []) else ""))
        if stage == "resumen":
            return self.reply(prefix + self.summary() + "\n\n¿Está bien así? Si algo no es, dime por ejemplo «el tomate es a 3.50».",
                              ["Sí, está bien"])
        return self.reply(prefix)

    def summary(self) -> str:
        d = self.doc
        lines = [f"Listo{', ' + d['owner'] if d.get('owner') else ''}. Así quedó tu negocio:"]
        for p in d["products"]:
            u = self.unit_txt(p)
            parts = []
            price = next((v.get("precio_cents") for v in p["vende_por"] if v.get("precio_cents")), None)
            if p.get("base") == "soles":
                parts.append("lo vendes de a sol")
            elif price:
                parts.append(f"lo vendes a {soles(price)} {'la' if u in ('unidad', 'docena') else 'el'} {u}")
            if p.get("costo_cents"):
                parts.append(f"te cuesta {soles(p['costo_cents'])}")
            c = p.get("compra_por") or {}
            if c.get("unidad") and c["unidad"] != p.get("base"):
                parts.append(f"compras por {c['unidad']}" + (f" de {units.fmt_qty(c['equivale'])} {'kg' if p.get('base') == 'kg' else 'unid.'}" if c.get("equivale") else ""))
            st = p.get("stock_inicial")
            if st:
                parts.append(f"te quedan {units.fmt_qty(st['cantidad'])} {units.unit_name(st['unidad'], st['cantidad'])}")
            lines.append(f"• {p['name']}: " + (", ".join(parts) if parts else "sin datos todavía"))
        methods = d.get("methods") or ["efectivo", "yape"]
        lines.append("Te pagan " + (" y por ".join("en efectivo" if m == "efectivo" else "Yape" for m in methods)) + ".")
        if d.get("expenses"):
            from . import costs
            lines.append("Tus gastos:")
            lines += ["• " + costs.line(i) for i in d["expenses"]]
            lines.append(costs.totals_text(d["expenses"]))
        if d.get("balances"):
            lines.append("Tienes " + " y ".join(f"{soles(v)} en {'efectivo' if k == 'efectivo' else 'Yape'}" for k, v in d["balances"].items()) + ".")
        return "\n".join(lines)

    # ------------------------------------------------------------ respuestas
    def handle(self, text: str) -> dict[str, Any]:
        t = nlu.normalize(text)
        d = self.doc
        stage = d.get("stage")
        if stage is None:
            prefix = ""
            if re.search(r"\b(vendi|gaste|compre|pague)\b", t):
                prefix = "Antes de anotar tus ventas, conozcamos tu negocio: son unas preguntas rápidas. "
            return self.ask("nombre", prefix)
        if stage not in ("precio", "compra", "stock", "gastos", "plata", "resumen") and re.match(r"^(vendi|gaste|compre|pague)\b", t):
            left = len(STAGES) - STAGES.index(stage)
            return self.ask(stage, f"Anoto tus ventas apenas terminemos (faltan {left} preguntas). ")
        return getattr(self, f"on_{stage}")(text, t)

    def on_nombre(self, raw: str, t: str):
        name = re.sub(r"^(hola|buenas|buenos dias|buenas tardes|buenas noches)\b\s*", "", t)
        name = re.sub(r"^(me llamo|soy|mi nombre es|yo soy)\s+", "", name)
        words = [w for w in name.split() if w not in ("la", "el", "senora", "sra", "don", "dona")]
        if not words:
            return self.ask("nombre")
        self.doc["owner"] = " ".join(w.capitalize() for w in words[:2])
        self.b.owner_name = self.doc["owner"]
        return self.ask("vende")

    def on_vende(self, raw: str, t: str):
        d = self.doc
        kind = guess_kind(raw)
        d["kind"] = d.get("kind") if d.get("kind") and not d["products"] else kind
        self.b.description = raw if not self.b.description else self.b.description
        names = extract_names(raw)
        if not names:
            hint = category_hint(nlu.normalize(raw))
            q = (f"¡Qué bien! ¿Qué {hint[0]} vendes más? Dime 3 o 4, por ejemplo «{hint[1]}»." if hint
                 else "¿Qué es lo que más vendes? Dime 3 o 4 cosas, separadas por comas.")
            d["stage"] = "vende"
            return self.reply(q)
        d["products"] = [_product(n) for n in names]
        if self.b.name in (None, "", "Mi negocio"):
            self.b.name = {"verduras": "Mi verdulería", "comida": "Mi cocina", "servicios": "Mi negocio"}.get(d["kind"], "Mi negocio")
            if d.get("owner"):
                self.b.name = f"{self.b.name.replace('Mi ', '').capitalize()} de {d['owner'].split()[0]}"
        return self.ask("mas")

    def on_mas(self, raw: str, t: str):
        d = self.doc
        if DONE_RE.match(t) or DONT_KNOW_RE.search(t):
            d["default_unit"] = {"verduras": "kg", "comida": "plato"}.get(d.get("kind"), "unidad")
            return self.ask("como")
        new = [n for n in extract_names(raw) if n.lower() not in [p["name"].lower() for p in d["products"]]]
        if not new:
            return self.ask("mas", "No te entendí bien. ")
        d["products"] += [_product(n) for n in new]
        return self.ask("mas")

    def on_como(self, raw: str, t: str):
        d = self.doc
        segs = segments(raw)
        default = None
        for seg in segs:
            us = _units_in(seg)
            if not us:
                continue
            idxs = _find(d, seg)
            if idxs:
                for i in idxs:
                    d["products"][i]["base"] = us[0]
            elif default is None:
                default = us[0]
        if default is None and not any(p.get("base") for p in d["products"]):
            default = d.get("default_unit") or ("kg" if d.get("kind") == "verduras" else "unidad")
            if not _units_in(t) and not DONT_KNOW_RE.search(t) and not DONE_RE.match(t):
                return self.ask("como", "No te entendí bien. ")
        d["default_unit"] = default or d.get("default_unit") or "unidad"
        for p in d["products"]:
            p["base"] = p.get("base") or d["default_unit"]
            p["vende_por"] = [{"unidad": p["base"]}]
        d["i"] = 0
        d["pending"] = None
        return self.ask("precio")

    def _next_product(self):
        d = self.doc
        d["pending"] = None
        d["i"] += 1
        if d["i"] >= len(d["products"]):
            d["i"] = 0
            return self.ask("compra")
        return self.ask("precio")

    def on_precio(self, raw: str, t: str):
        d = self.doc
        p = d["products"][d["i"]]
        if d.get("pending") == "costo":
            amts = _money(t)
            if amts and not DONT_KNOW_RE.search(t):
                p["costo_cents"] = amts[0]
            return self._next_product()
        us = [u for u in _units_in(t) if u in ("kg", "unidad", "atado", "docena", "plato", "soles")]
        if us and us[0] != p.get("base"):
            p["base"] = us[0]
            p["vende_por"] = [{"unidad": us[0]}]
        if p.get("base") == "soles":
            amts = _money(t)
            p["vende_por"] = [{"unidad": "soles", "montos_cents": amts}] if amts else [{"unidad": "soles"}]
            return self._next_product()
        if DONT_KNOW_RE.search(t) and not _money(t):
            return self._next_product()
        amts = _money(t)
        if not amts:
            return self.ask("precio", "No te entendí bien. ")
        price = cost = None
        mcost = re.search(r"(me cuesta|me sale|lo compro|a mi|me lo dejan|compro a|pago)\D{0,12}(\d+(?:\.\d{1,2})?)", t)
        if mcost:
            cost = int(round(float(mcost.group(2)) * 100))
            rest = [a for a in amts if a != cost]
            price = rest[0] if rest else None
        else:
            price = amts[0]
            cost = amts[1] if len(amts) > 1 else None
        if price:
            p["vende_por"] = [{"unidad": p["base"], "precio_cents": price}]
        if cost:
            p["costo_cents"] = cost
            return self._next_product()
        d["pending"] = "costo"
        return self.ask("precio")

    def on_compra(self, raw: str, t: str):
        d = self.doc
        pend = d.get("pending")
        if pend and pend.startswith("equiv:"):
            idx = int(pend.split(":")[1])
            p = d["products"][idx]
            m = re.search(r"(\d+(?:\.\d+)?)", t)
            if m and not DONT_KNOW_RE.search(t):
                p["compra_por"]["equivale"] = float(m.group(1))
                if p["compra_por"].get("costo_cents") and not p.get("costo_cents"):
                    p["costo_cents"] = round(p["compra_por"]["costo_cents"] / float(m.group(1)))
            d["pending"] = None
            return self._after_compra()
        if DONT_KNOW_RE.search(t) or DONE_RE.match(t):
            return self.ask("stock")
        segs = segments(raw)
        general = None
        for seg in segs:
            us = [u for u in _units_in(seg) if u != "soles"]
            if not us:
                continue
            unit = next((u for u in us if u in PACKS), us[0])
            m_eq = re.search(r"(?:de|trae|con|por)\s+(\d+(?:\.\d+)?)\s*(kilos?|kg|unidades)", seg)
            if m_eq and m_eq.group(2) == "unidades" and float(m_eq.group(1)) > 1 and unit == "unidad":
                unit = "docena" if float(m_eq.group(1)) == 12 else "paquete"   # «por docena» llega como «por 12 unidades»
            money = [a for a in _money(re.sub(r"(\d+(?:\.\d+)?)\s*(kilos?|kg|unidades)", " ", seg))]
            info = {"unidad": unit}
            if m_eq:
                info["equivale"] = float(m_eq.group(1))
            elif unit == "docena":
                info["equivale"] = 12.0
            if money:
                info["costo_cents"] = money[-1]
            idxs = _find(d, seg)
            if not idxs:
                general = info
                continue
            for i in idxs:
                self._set_compra(d["products"][i], info)
        if general:
            for p in d["products"]:
                if not p.get("compra_por"):
                    self._set_compra(p, dict(general))
        return self._after_compra()

    def _set_compra(self, p: dict[str, Any], info: dict[str, Any]):
        base = p.get("base")
        if info["unidad"] == base:
            info.pop("equivale", None)
        p["compra_por"] = info
        if info.get("costo_cents"):
            if info["unidad"] == base:
                p.setdefault("costo_cents", info["costo_cents"])
            elif info.get("equivale") and not p.get("costo_cents"):
                p["costo_cents"] = round(info["costo_cents"] / info["equivale"])

    def _after_compra(self):
        d = self.doc
        for i, p in enumerate(d["products"]):
            c = p.get("compra_por") or {}
            if c.get("unidad") in PACKS and c["unidad"] != "docena" and p.get("base") == "kg" and not c.get("equivale") and not c.get("_asked"):
                c["_asked"] = True
                d["pending"] = f"equiv:{i}"
                return self.ask("compra")
        d["pending"] = None
        return self.ask("stock")

    def on_stock(self, raw: str, t: str):
        d = self.doc
        if DONT_KNOW_RE.search(t) or DONE_RE.match(t):
            return self.ask("pago")
        segs = segments(raw)
        found = False
        for seg in segs:
            idxs = _find(d, seg)
            if not idxs:
                continue
            p = d["products"][idxs[0]]
            m = re.search(r"(\d+(?:\.\d+)?)\s*(kilos?|kg|jabas?|sacos?|cajas?|atados?|docenas?|bolsas?|unidades|paquetes?)?", seg)
            if not m:
                continue
            qty = float(m.group(1))
            unit = next((u for pat, u in UNIT_WORDS if m.group(2) and re.match(pat, m.group(2))), None) or p.get("base") or "unidad"
            ref = nlu.ProductRef(0, p["name"], p["aliases"])
            fake = type("P", (), {"spec": {"base": p.get("base"), "compra_por": p.get("compra_por") or {}}, "unit": p.get("base")})()
            en_base = units.to_base(fake, qty, unit)
            p["stock_inicial"] = {"cantidad": qty, "unidad": unit, "en_base": en_base}
            found = True
            del ref
        if not found:
            return self.ask("stock", "No te entendí bien. ")
        return self.ask("pago")

    def on_pago(self, raw: str, t: str):
        d = self.doc
        if re.search(r"\b(dos|ambas|ambos|los 2|las 2|todo)\b", t) or ("yape" in t and "efectivo" in t):
            d["methods"] = ["efectivo", "yape"]
        elif re.search(r"\b(yape|plin)\b", t):
            d["methods"] = ["yape"]
        elif re.search(r"\b(efectivo|cash|billete|sencillo)\b", t):
            d["methods"] = ["efectivo"]
        else:
            return self.ask("pago", "No te entendí bien. ")
        d["pending"] = None
        return self.ask("gastos")

    def on_gastos(self, raw: str, t: str):
        from . import costs
        d = self.doc
        exp = d.setdefault("expenses", [])
        pend = d.get("pending") or ""
        if pend.startswith("gfreq:"):
            i = int(pend.split(":")[1])
            freq = costs.find_frequency(t) or {"dia": "diario", "semana": "semanal", "mes": "mensual", "ano": "anual",
                                               "quincena": "quincenal"}.get(t.split()[-1] if t.split() else "", None)
            if not freq:
                return self.ask("gastos", "No te entendí. ")
            exp[i]["frequency"] = freq
            exp[i]["cost_type"] = costs.classify(exp[i]["name"], freq)
            d["pending"] = None
            return self._next_missing_freq()
        if (DONE_RE.match(t) or DONT_KNOW_RE.search(t)) and not re.search(r"\d", t):
            d["pending"] = None
            return self.ask("plata")
        items = costs.parse(raw)
        if not items:
            return self.ask("gastos", "No te entendí bien. Dime qué pagas, cuánto y cada cuánto. ")
        names = {e["name"].lower() for e in exp}
        for it in items:
            if it["name"].lower() in names:     # lo repitió: actualizo
                exp[:] = [e for e in exp if e["name"].lower() != it["name"].lower()]
            exp.append(it)
        return self._next_missing_freq()

    def _next_missing_freq(self):
        d = self.doc
        for i, e in enumerate(d.get("expenses") or []):
            if not e.get("frequency"):
                d["pending"] = f"gfreq:{i}"
                return self.ask("gastos")
        d["pending"] = None
        return self.ask("gastos")

    def on_plata(self, raw: str, t: str):
        d = self.doc
        bal = dict(d.get("balances") or {})
        if d.get("pending") == "yape":
            amts = _money(t)
            bal["yape"] = amts[0] if amts and not DONT_KNOW_RE.search(t) else 0
            d["balances"] = bal
            d["pending"] = None
            return self.ask("resumen")
        parsed = nlu._balances(t) if _money(t) else {}
        if not parsed and not DONT_KNOW_RE.search(t):
            return self.ask("plata", "No te entendí bien. ")
        bal.update(parsed)
        d["balances"] = bal
        if "yape" in d.get("methods", []) and "yape" not in bal:
            d["pending"] = "yape"
            return self.ask("plata")
        return self.ask("resumen")

    def on_resumen(self, raw: str, t: str):
        d = self.doc
        if nlu.CONFIRM_RE.match(t) or re.match(r"^(si|esta bien|correcto|asi es|todo bien)\b", t):
            return self.finish()
        changed = False
        m_del = re.match(r"^(quita|borra|elimina|ya no vendo)\s+(?:el |la |los |las )?(.+)$", t)
        if m_del:
            idxs = _find(d, m_del.group(2))
            d["products"] = [p for i, p in enumerate(d["products"]) if i not in idxs]
            changed = bool(idxs)
        m_add = re.match(r"^(agrega|anade|tambien vendo)\s+(?:el |la |los |las )?([a-zñ ]+?)(?:\s+a\s+|\s*$)", t)
        if m_add and not changed:
            name = extract_names(m_add.group(2))
            if name:
                p = _product(name[0])
                p["base"] = d.get("default_unit") or "unidad"
                amts = _money(t)
                p["vende_por"] = [{"unidad": p["base"], **({"precio_cents": amts[0]} if amts else {})}]
                d["products"].append(p)
                changed = True
        if not changed:
            idxs = _find(d, t)
            amts = _money(t)
            if idxs and amts:
                p = d["products"][idxs[0]]
                if re.search(r"(cuesta|compro|me sale|costo)", t):
                    p["costo_cents"] = amts[0]
                else:
                    p["vende_por"] = [{"unidad": p.get("base") or "unidad", "precio_cents": amts[0]}]
                changed = True
        if not changed:
            return self.ask("resumen", "No te entendí. Dime por ejemplo «el tomate es a 3.50», «agrega rocoto a 8» o «quita el ajo». ")
        return self.ask("resumen", "Corregido. ")

    # ------------------------------------------------------------ guardar
    def finish(self) -> dict[str, Any]:
        d = self.doc
        b = self.b
        kind = d.get("kind") or "reventa"
        b.kind = kind
        b.payment_methods = d.get("methods") or ["efectivo", "yape"]
        for c in TEMPLATES.get(kind, TEMPLATES["reventa"])["categories"]:
            self.db.add(M.Category(business_id=b.id, name=c["name"], kind=c["kind"]))
        existing = {x.name.lower(): x for x in self.db.scalars(select(M.Product).where(M.Product.business_id == b.id)).all()}
        for p in d["products"]:
            base = p.get("base") or "unidad"
            price = next((v.get("precio_cents") for v in p["vende_por"] if v.get("precio_cents")), None)
            st = p.get("stock_inicial") or {}
            compra = {k: v for k, v in (p.get("compra_por") or {}).items() if not k.startswith("_")}
            spec = {"base": base, "vende_por": p["vende_por"], "compra_por": compra,
                    **({"stock_inicial": st} if st else {}), "creado_por": "conversacion"}
            prod = existing.get(p["name"].lower()) or M.Product(business_id=b.id, name=p["name"])
            prod.aliases = p["aliases"]
            prod.unit = base
            prod.spec = spec
            prod.price_cents = price
            prod.cost_cents = p.get("costo_cents")
            prod.is_service = kind == "servicios"
            prod.initial_stock = st.get("en_base")
            prod.track_stock = st.get("en_base") is not None or (kind == "reventa" and base == "unidad")
            if prod.track_stock and prod.initial_stock is None and kind == "reventa":
                prod.initial_stock = None
            self.db.add(prod)
        for e in d.get("expenses") or []:
            fx = self.db.scalar(select(M.FixedExpense).where(M.FixedExpense.business_id == b.id, M.FixedExpense.name == e["name"]))
            fx = fx or M.FixedExpense(business_id=b.id, name=e["name"])
            fx.amount_cents = e["amount_cents"]
            fx.frequency = e.get("frequency") or "mensual"
            fx.cost_type = e.get("cost_type") or "fijo"
            fx.due_day = e.get("due_day") or 1
            self.db.add(fx)
        first = now_lima() - timedelta(minutes=1)
        for pocket, cents in (d.get("balances") or {}).items():
            if pocket in M.POCKETS and cents is not None:
                ledger.record(self.db, b, {"kind": M.OPENING, "method": pocket, "amount_cents": int(cents), "occurred_at": first,
                                           "description": "Saldo inicial (primera conversación)"},
                              op_id=f"setup-{b.id}-{pocket}", channel=self.eng.channel, commit=False)
        b.setup_state = "listo"
        b.setup_source = "conversacion"
        d["stage"] = "listo"
        ex = "«vendí 3 soles de tomate y un kilo de papa en efectivo»" if kind == "verduras" else "«vendí 2 polos a 20 por Yape»"
        return self.reply(f"¡Todo listo{', ' + d['owner'] if d.get('owner') else ''}! 🎉 Ya tengo tu lista de productos y tu caja. "
                          f"Desde ahora, cuando vendas algo mándame un audio, por ejemplo {ex}. Se guarda al toque. "
                          "En la noche dime «cerrar mi día» y cuadramos tu plata.", ["Ver mi negocio"], done=True)


def handle(eng, text: str) -> dict[str, Any]:
    return Onboarding(eng).handle(text)
