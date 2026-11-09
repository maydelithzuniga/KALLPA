"""Gastos que paga el negocio: qué, cuánto, cada cuánto y si es costo fijo o variable.

Se preguntan en la primera conversación («¿qué pagas y cada cuánto?») y también se pueden decir
después por chat («pago 250 de alquiler al mes», «bolsas 15 a la semana»).

- Fijo: lo pagas vendas o no (alquiler, luz, celular, ayudante, licencia, pasaje diario al puesto).
- Variable: sube cuando vendes o compras más (bolsas, flete, estiba, gas de la cocina, delivery).

Todo se lleva a «cuánto es al mes» para el punto de equilibrio, la caja y el informe.
"""
from __future__ import annotations

import re
from typing import Any

from . import nlu
from .money import soles

# veces por mes de cada frecuencia
FREQ_PER_MONTH = {"diario": 30.0, "semanal": 52 / 12, "quincenal": 2.0, "mensual": 1.0, "anual": 1 / 12}
FREQ_LABEL = {"diario": "al día", "semanal": "a la semana", "quincenal": "cada quincena", "mensual": "al mes", "anual": "al año"}
FREQ_PATTERNS = [
    ("diario", r"\b(al dia|diarios?|diaria|diariamente|cada dia|por dia|todos los dias|el dia)\b"),
    ("semanal", r"\b(a la semana|semanal(?:es)?|semanalmente|cada semana|por semana|(?:los|cada) (?:lunes|martes|miercoles|jueves|viernes|sabados?|domingos?))\b"),
    ("quincenal", r"\b(quincenal(?:es)?|cada quincena|a la quincena|cada 15 dias|por quincena)\b"),
    ("mensual", r"\b(al mes|mensual(?:es)?|mensualmente|cada mes|por mes|mes a mes|de cada mes)\b"),
    ("anual", r"\b(al ano|anual(?:es)?|anualmente|cada ano|por ano|una vez al ano)\b"),
]
FIXED_RE = re.compile(r"\b(alquiler|renta|luz|agua|internet|cable|celular|telefono|recarga|sueldos?|ayudantes?|trabajador(?:a|es)?|"
                      r"empleados?|licencia|municipalidad|municipal|sisa|arbitrios|seguro|vigilancia|guardian|cochera|"
                      r"prestamo|cuota|contador|impuestos?|sunat|mantenimiento|pasajes?|movilidad|taxi|mototaxi|combi|"
                      r"local|puesto|stand|limpieza|asociacion|junta)\b")
VARIABLE_RE = re.compile(r"\b(bolsas?|empaques?|tapers?|envases?|descartables|flete|fletes|carga|estiba|cargador|"
                         r"delivery|gas|balon|hielo|carbon|lena|insumos?|comision(?:es)?|gasolina|combustible|"
                         r"etiquetas|papel)\b")
FILLER = {"pago", "pagos", "pagamos", "pague", "gasto", "gastos", "gastamos", "de", "del", "el", "la", "los", "las", "en", "por",
          "soles", "sol", "me", "sale", "salen", "cuesta", "cuestan", "unos", "unas", "como", "mas", "o", "menos", "s", "y",
          "a", "al", "cada", "un", "una", "tambien", "aparte", "ademas", "que", "es", "son", "para", "mi", "mis", "negocio",
          "aproximadamente", "promedio", "tengo", "doy", "le", "les", "todo", "total"}


def find_frequency(t: str) -> str | None:
    for freq, pat in FREQ_PATTERNS:
        if re.search(pat, t):
            return freq
    return None


def classify(name: str, freq: str | None) -> str:
    n = nlu.normalize(name)
    if VARIABLE_RE.search(n):
        return "variable"
    if FIXED_RE.search(n):
        return "fijo"
    return "fijo" if freq in ("mensual", "anual", "quincenal") else "variable"


def monthly_cents(amount_cents: int, freq: str | None) -> int:
    return round(amount_cents * FREQ_PER_MONTH.get(freq or "mensual", 1.0))


def _clean_name(seg: str) -> str:
    s = seg
    for _f, pat in FREQ_PATTERNS:
        s = re.sub(pat, " ", s)
    s = re.sub(r"(?:s/ ?)?\d+(?:\.\d+)?", " ", s)
    s = re.sub(r"\b(el|los) \d{1,2}\b", " ", s)
    edges = {"de", "del", "la", "el", "los", "las", "y", "al", "a", "en", "por", "para", "un", "una"}
    words = [w for w in s.split() if (w not in FILLER or w in edges) and len(w) > 1 or w in ("de", "y")]
    while words and words[0] in edges:
        words.pop(0)
    while words and words[-1] in edges:
        words.pop()
    return " ".join(words[:5])


def _amount(seg: str) -> int | None:
    m = re.search(r"(?:s/ ?)?(\d+(?:\.\d{1,2})?)(?! de cada)(?!\s*(?:de|del) (?:cada )?mes)", seg)
    if not m:
        return None
    # «el 5 de cada mes» es el día de pago, no el monto
    for mm in re.finditer(r"(?:s/ ?)?(\d+(?:\.\d{1,2})?)", seg):
        before = seg[max(0, mm.start() - 4):mm.start()]
        after = seg[mm.end():mm.end() + 12]
        if re.search(r"\b(el|los) $", before) and re.match(r"\s*(de cada mes|de mes|de cada|$)", after):
            continue
        return int(round(float(mm.group(1)) * 100))
    return None


def _due_day(seg: str) -> int | None:
    m = re.search(r"\b(?:el|los) (\d{1,2})(?: de cada mes| de mes|\b)", seg)
    if m and 1 <= int(m.group(1)) <= 31:
        return int(m.group(1))
    return None


def parse(raw: str) -> list[dict[str, Any]]:
    """«alquiler 250 al mes, luz y agua 40 al mes, pasaje 10 al día» → lista de gastos.
    Una frecuencia dicha al final vale para los anteriores que no la dijeron («alquiler 250 y luz 40 al mes»)."""
    from .onboarding import segments
    items: list[dict[str, Any]] = []
    carry: list[str] = []
    for seg in segments(raw):
        amt = _amount(seg)
        name = _clean_name(seg)
        if amt is None:
            if name:
                carry.append(name)        # «luz y agua 40»: «luz» espera a su monto
            elif items and find_frequency(seg) and not items[-1]["frequency"]:
                items[-1]["frequency"] = find_frequency(seg)
            continue
        full = " y ".join(carry + ([name] if name else [])) or "Gasto"
        carry = []
        items.append({"name": full[:1].upper() + full[1:], "amount_cents": amt, "frequency": find_frequency(seg),
                      "due_day": _due_day(seg)})
    # frecuencia compartida: la última dicha cubre a los anteriores sin frecuencia
    nxt = None
    for it in reversed(items):
        if it["frequency"]:
            nxt = it["frequency"]
        elif nxt:
            it["frequency"] = nxt
    for it in items:
        it["cost_type"] = classify(it["name"], it["frequency"])
    return items


def line(it: dict[str, Any]) -> str:
    tipo = "fijo" if it.get("cost_type", "fijo") == "fijo" else "variable"
    return f"{it['name']} {soles(it['amount_cents'])} {FREQ_LABEL.get(it.get('frequency') or 'mensual')} ({tipo})"


def totals_text(items: list[dict[str, Any]]) -> str:
    fixed = sum(monthly_cents(i["amount_cents"], i.get("frequency")) for i in items if i.get("cost_type") == "fijo")
    var = sum(monthly_cents(i["amount_cents"], i.get("frequency")) for i in items if i.get("cost_type") != "fijo")
    parts = []
    if fixed:
        parts.append(f"{soles(fixed)} fijos")
    if var:
        parts.append(f"{soles(var)} variables")
    return f"Al mes son unos {soles(fixed + var)}" + (f" ({' y '.join(parts)})" if parts else "") + "."


def explain_types() -> str:
    return ("Fijo = lo pagas vendas o no (alquiler, luz, celular). Variable = sube cuando vendes más (bolsas, flete).")
