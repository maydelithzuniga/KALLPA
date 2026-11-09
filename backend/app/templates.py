"""Plantillas locales: se usan sin IA externa o si Gemini falla."""
from __future__ import annotations

VEG = [  # nombre, alias, unidad
    ("Tomate", ["tomates", "tomatito"], "kg"), ("Papa", ["papas", "papita", "papa amarilla", "papa blanca"], "kg"),
    ("Cebolla", ["cebollas", "cebollita", "cebolla roja"], "kg"), ("Limón", ["limon", "limones"], "kg"),
    ("Zanahoria", ["zanahorias"], "kg"), ("Ají", ["aji", "ajies", "ajíes", "ají amarillo"], "kg"),
    ("Culantro", ["culantrito"], "atado"), ("Lechuga", ["lechugas"], "unidad"), ("Choclo", ["choclos"], "unidad"),
    ("Ajo", ["ajos"], "kg"), ("Zapallo", ["zapallito"], "kg"), ("Pimiento", ["pimientos"], "kg"),
]

TEMPLATES: dict[str, dict] = {
    "verduras": {
        "label": "Verdulería (verduras y frutas por kilo)",
        "categories": [
            {"name": "Venta de verduras", "kind": "venta"},
            {"name": "Compra en el mayorista", "kind": "compra"},
            {"name": "Alquiler del puesto", "kind": "gasto_fijo"},
            {"name": "Luz y agua", "kind": "gasto_fijo"},
            {"name": "Bolsas", "kind": "gasto_variable"},
            {"name": "Flete y carretilla", "kind": "gasto_variable"},
            {"name": "Gastos de la casa", "kind": "personal"},
        ],
        "products": [{"name": n, "aliases": a, "unit": u, "track_stock": False} for n, a, u in VEG],
    },
    "reventa": {
        "label": "Reventa (compro y vendo productos)",
        "categories": [
            {"name": "Venta de productos", "kind": "venta"},
            {"name": "Compra de mercadería", "kind": "compra"},
            {"name": "Alquiler", "kind": "gasto_fijo"},
            {"name": "Luz y agua", "kind": "gasto_fijo"},
            {"name": "Internet y celular", "kind": "gasto_fijo"},
            {"name": "Movilidad y fletes", "kind": "gasto_variable"},
            {"name": "Bolsas y empaques", "kind": "gasto_variable"},
            {"name": "Gastos de la casa", "kind": "personal"},
        ],
        "products": [
            {"name": "Polo básico", "aliases": ["polo", "polos", "polito", "politos", "polo basico"]},
        ],
    },
    "comida": {
        "label": "Comida preparada (menú, jugos, postres)",
        "categories": [
            {"name": "Venta de platos", "kind": "venta"},
            {"name": "Insumos de cocina", "kind": "compra"},
            {"name": "Gas", "kind": "gasto_fijo"},
            {"name": "Alquiler", "kind": "gasto_fijo"},
            {"name": "Luz y agua", "kind": "gasto_fijo"},
            {"name": "Sueldo de ayudante", "kind": "gasto_fijo"},
            {"name": "Descartables", "kind": "gasto_variable"},
            {"name": "Gastos de la casa", "kind": "personal"},
        ],
        "products": [
            {"name": "Menú", "aliases": ["menu", "menus", "menús", "plato", "platos", "almuerzo", "almuerzos"], "track_stock": False},
            {"name": "Jugo", "aliases": ["jugos", "juguito", "juguitos"], "track_stock": False},
            {"name": "Aceite", "aliases": ["aceite", "aceites"], "is_input": True, "unit": "litro", "track_stock": False},
        ],
    },
    "servicios": {
        "label": "Servicios (peluquería, costura, uñas, reparaciones)",
        "categories": [
            {"name": "Cobro de servicios", "kind": "venta"},
            {"name": "Materiales e insumos", "kind": "compra"},
            {"name": "Alquiler", "kind": "gasto_fijo"},
            {"name": "Luz y agua", "kind": "gasto_fijo"},
            {"name": "Movilidad", "kind": "gasto_variable"},
            {"name": "Gastos de la casa", "kind": "personal"},
        ],
        "products": [
            {"name": "Servicio", "aliases": ["servicio", "servicios", "atencion", "atenciones"], "is_service": True, "track_stock": False},
        ],
    },
}


def guess_kind(description: str) -> str:
    t = (description or "").lower()
    veg = ["verdura", "fruta", "tomate", "papa", "cebolla", "limón", "limon", "zanahoria", "mercado de abastos", "mayorista", "hortaliza"]
    if any(w in t for w in veg):
        return "verduras"
    food = ["menu", "menú", "comida", "plato", "jugo", "cocina", "salchipapa", "postre", "queque", "pollo", "desayuno", "almuerzo", "anticucho", "emoliente", "ceviche"]
    service = ["corte", "peluquer", "uñas", "costura", "arreglo", "reparo", "reparación", "servicio", "masaje", "manicure", "maquillaje", "clases", "lavado"]
    if any(w in t for w in food):
        return "comida"
    if any(w in t for w in service):
        return "servicios"
    return "reventa"


def local_proposal(description: str, kind: str | None = None) -> dict:
    """Propuesta local a partir del rubro. Precios, costos y stock quedan desconocidos."""
    from .nlu import extract_product_names

    kind = kind or guess_kind(description)
    tpl = TEMPLATES[kind]
    products = [dict(p) for p in tpl["products"]]
    names = extract_product_names(description)
    if names and kind != "verduras":
        products = [p for p in products if p.get("is_input")]
        for n in names:
            singular = n[:-1] if n.endswith("s") and len(n) > 3 else n
            products.append({
                "name": singular.capitalize(),
                "aliases": sorted({singular, singular + "s", n}),
                "is_service": kind == "servicios",
                "track_stock": kind == "reventa",
            })
    t = (description or "").lower()
    methods = [m for m in ("efectivo", "yape") if m in t] or ["efectivo", "yape"]
    return {
        "kind": kind,
        "business_name": None,
        "categories": tpl["categories"],
        "products": products,
        "payment_methods": methods,
        "source": "plantilla",
    }
