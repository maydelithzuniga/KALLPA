"""Datos de demostración (ficticios). Se marcan como demo y el reporte lo indica."""
from __future__ import annotations

import random
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import ledger, reconcile
from . import models as M
from .templates import TEMPLATES
from .timeutil import add_months, month_start, today_lima

PAYERS = ["Lucía Q.", "Marco T.", "Ana R.", "Jorge P.", "Milagros C.", "Rosa M.", "Pedro V.", "Karina S.",
          "Luis H.", "Carmen D.", "Diana F.", "Wilber A.", "Sofía L.", "Elena G.", "Raúl N.", "Gladys B.",
          "Yesenia O.", "Héctor J.", "Flor E.", "Nancy Z.", "Iván K.", "Paola W."]
WD_FACTOR = {0: 0.6, 1: 0.85, 2: 0.9, 3: 0.95, 4: 1.1, 5: 1.5, 6: 1.3}


def _dt(d: date, hour: int, minute: int = 0) -> datetime:
    return datetime(d.year, d.month, d.day, hour, minute)


class _Op:
    def __init__(self, prefix: str):
        self.prefix = prefix
        self.n = 0

    def __call__(self) -> str:
        self.n += 1
        return f"{self.prefix}-{self.n}"


def _verify_yape(db: Session, b: M.Business, rng: random.Random, kinds: tuple[str, ...], rate: float = 0.9) -> None:
    """Crea los registros de Yape (demo) de los movimientos por Yape y los verifica (no todos: algunos quedan sin verificar)."""
    db.flush()
    mvs = db.scalars(select(M.Movement).where(M.Movement.business_id == b.id, M.Movement.method == "yape",
                                              M.Movement.kind.in_(kinds), M.Movement.status == "confirmado")).all()
    linked = set(db.scalars(select(M.YapePayment.movement_id).where(M.YapePayment.business_id == b.id,
                                                                    M.YapePayment.movement_id.is_not(None))).all())
    n = 0
    for mv in mvs:
        if mv.id in linked or not mv.paid_cents or rng.random() > rate:
            continue
        n += 1
        direction = "entrada" if mv.kind in M.YAPE_IN_KINDS else "salida"
        who = mv.counterparty or (rng.choice(PAYERS) if direction == "entrada" else (mv.category or "Pago"))
        db.add(M.YapePayment(business_id=b.id, direction=direction, payer=who, amount_cents=mv.paid_cents,
                             received_at=mv.occurred_at + timedelta(minutes=1), operation_code=f"DEMO-{b.id}-{direction[0]}{n:05d}",
                             movement_id=mv.id, demo=True))
        mv.origin = "respaldo_yape"
    db.flush()


def _rebalance(db: Session, b: M.Business, d: date, op) -> None:
    """Pasa plata de Yape a efectivo cuando el efectivo baja (como haría la emprendedora)."""
    bal = ledger.pocket_balances(db, b.id)
    if bal["efectivo"] < 30000 and bal["yape"] > 40000:
        amount = min(bal["yape"] - 20000, ((60000 - bal["efectivo"]) // 10000 + 1) * 10000)
        ledger.record(db, b, {"kind": M.TRANSFER, "method": "yape", "to_method": "efectivo", "amount_cents": amount,
                              "occurred_at": _dt(d, 21, 30)}, op_id=op(), channel="demo", demo=True, commit=False)
        db.flush()


def seed_resale(db: Session, days: int = 95) -> M.Business:
    rng = random.Random(11)
    today = today_lima()
    start = today - timedelta(days=days)
    b = M.Business(name="Polos Rosita", owner_name="Rosa", kind="reventa", demo=True, setup_state="listo",
                   setup_source="plantilla", description="Vendo polos, blusas, shorts y gorras en el mercado. Compro por docena y cobro por Yape y en efectivo.",
                   phone="51900000001", created_at=_dt(start, 8))
    db.add(b)
    db.flush()
    for c in TEMPLATES["reventa"]["categories"]:
        db.add(M.Category(business_id=b.id, name=c["name"], kind=c["kind"]))
    specs = [("Polo básico", ["polo", "polos", "polito", "politos", "polo basico"], 2000, 1200, 40),
             ("Blusa", ["blusas", "blusita"], 3500, 2000, 20),
             ("Short", ["shorts", "chor", "chores"], 2500, 1400, 20),
             ("Gorra", ["gorras", "gorrita", "gorro"], 1500, 800, 25)]
    prods = []
    for name, aliases, price, cost, stock in specs:
        p = M.Product(business_id=b.id, name=name, aliases=aliases, price_cents=price, cost_cents=cost,
                      initial_stock=stock, reorder_point=8, track_stock=True)
        db.add(p)
        prods.append(p)
    db.flush()
    db.add_all([M.FixedExpense(business_id=b.id, name="Alquiler", amount_cents=40000, due_day=1),
                M.FixedExpense(business_id=b.id, name="Luz y agua", amount_cents=6000, due_day=10),
                M.FixedExpense(business_id=b.id, name="Internet y celular", amount_cents=4000, due_day=5)])
    debt = M.Debt(business_id=b.id, creditor="Caja de ejemplo", total_cents=300000, installment_cents=25000, due_day=15,
                  installments_total=12)
    db.add(debt)
    db.add_all([M.Asset(business_id=b.id, name="Exhibidor y maniquíes", value_cents=45000),
                M.Asset(business_id=b.id, name="Mesa plegable y toldo", value_cents=18000)])
    db.flush()
    op = _Op(f"demo-{b.id}")
    ledger.record(db, b, {"kind": M.OPENING, "method": "efectivo", "amount_cents": 30000, "occurred_at": _dt(start, 7)},
                  op_id=op(), channel="demo", demo=True, commit=False)
    ledger.record(db, b, {"kind": M.OPENING, "method": "yape", "amount_cents": 20000, "occurred_at": _dt(start, 7)},
                  op_id=op(), channel="demo", demo=True, commit=False)
    stock = {p.id: p.initial_stock for p in prods}
    goal = M.Goal(business_id=b.id, kind="ahorro", name="Abrir otro puesto", target_cents=300000,
                  deadline=today + timedelta(days=120), created_at=_dt(today - timedelta(days=40), 9))
    db.add(goal)
    db.add(M.Goal(business_id=b.id, kind="reposicion", name="Mercadería para la campaña navideña", target_cents=300000, created_at=_dt(today - timedelta(days=5), 9)))
    db.flush()
    yape_n = 0
    pending_fiados: list[M.Movement] = []
    d = start
    while d < today + timedelta(days=1):
        is_today = d == today
        n_sales = max(1, round(rng.gauss(7, 2) * WD_FACTOR[d.weekday()]))
        if is_today:
            n_sales = 4
        for i in range(n_sales):
            p = rng.choices(prods, weights=[5, 2, 3, 2])[0]
            qty = rng.choices([1, 2, 3], weights=[6, 3, 1])[0]
            if stock[p.id] < qty:
                continue
            ref = p.price_cents * qty
            total = ref - (rng.choice([0, 0, 0, 0, 500, 1000]) if qty > 1 else rng.choice([0, 0, 0, 0, 0, 200]))
            when = _dt(d, rng.randint(9, 19), rng.randint(0, 59))
            if is_today:   # las ventas de hoy, antes de la hora actual
                from .timeutil import now_lima
                now = now_lima()
                when = min(when, now - timedelta(minutes=10 * (n_sales - i)))
            method = "yape" if rng.random() < 0.62 else "efectivo"
            data = {"kind": M.SALE, "product_id": p.id, "quantity": qty, "amount_cents": total, "method": method,
                    "occurred_at": when, "raw_text": f"vendí {qty} {p.name.lower()} a {total // 100}"}
            fiado = rng.random() < 0.04 and not is_today
            if fiado:
                data["paid_cents"] = 0 if rng.random() < 0.5 else total // 2
                data["counterparty"] = rng.choice(["Juana", "Sra. Carmen", "Vecina Elsa", "Don Pepe"])
                if data["paid_cents"] == 0:
                    data["method"] = None
            if method == "yape" and data.get("paid_cents", total) > 0 and rng.random() < 0.88:
                yape_n += 1
                db.add(M.YapePayment(business_id=b.id, payer=rng.choice(PAYERS), amount_cents=data.get("paid_cents", total),
                                     received_at=when + timedelta(minutes=1), operation_code=f"DEMO{yape_n:05d}", demo=True))
                db.flush()
            mv, _ = ledger.record(db, b, data, op_id=op(), channel="demo", demo=True, commit=False)
            stock[p.id] -= qty
            if fiado:
                pending_fiados.append(mv)
        # cobro de fiados viejos
        for f in list(pending_fiados):
            if (d - f.occurred_at.date()).days >= rng.randint(5, 12) and rng.random() < 0.5:
                pend = ledger.sale_pending(db, f)
                if pend and (today - d).days > 3:
                    ledger.record(db, b, {"kind": M.COLLECTION, "parent_id": f.id, "amount_cents": pend, "method": "efectivo",
                                          "counterparty": f.counterparty, "occurred_at": _dt(d, 12)},
                                  op_id=op(), channel="demo", demo=True, commit=False)
                pending_fiados.remove(f)
        # reposición semanal
        if d.weekday() == 1 and not is_today:
            for p in prods:
                if stock[p.id] < 18:
                    qty = 24 if p.name != "Blusa" else 12
                    unit = p.cost_cents
                    if p.name == "Gorra" and (today - d).days < 7:
                        unit = 920
                    ledger.record(db, b, {"kind": M.PURCHASE, "product_id": p.id, "quantity": qty,
                                          "amount_cents": unit * qty, "method": rng.choice(["efectivo", "yape"]),
                                          "occurred_at": _dt(d, 7, 30), "counterparty": "Gamarra - Proveedor demo",
                                          "origin": "comprobante" if rng.random() < 0.6 else "autodeclarado"},
                                  op_id=op(), channel="demo", demo=True, commit=False)
                    stock[p.id] += qty
            db.add(M.Count(business_id=b.id, kind="stock", product_id=prods[0].id, counted=stock[prods[0].id],
                           expected=stock[prods[0].id], difference=0, result="consistente", review_status="revisado",
                           counted_at=_dt(d, 20), demo=True))
        # gastos fijos y variables
        if d.day == 1:
            ledger.record(db, b, {"kind": M.EXPENSE, "category": "Alquiler", "expense_type": "fijo", "amount_cents": 40000,
                                  "method": "efectivo", "occurred_at": _dt(d, 8)}, op_id=op(), channel="demo", demo=True, commit=False)
        if d.day == 5:
            ledger.record(db, b, {"kind": M.EXPENSE, "category": "Internet y celular", "expense_type": "fijo", "amount_cents": 4000,
                                  "method": "yape", "occurred_at": _dt(d, 8)}, op_id=op(), channel="demo", demo=True, commit=False)
        if d.day == 10:
            ledger.record(db, b, {"kind": M.EXPENSE, "category": "Luz y agua", "expense_type": "fijo", "amount_cents": rng.choice([5500, 6000, 6400]),
                                  "method": "efectivo", "occurred_at": _dt(d, 8)}, op_id=op(), channel="demo", demo=True, commit=False)
        if d.day == 14:
            ledger.record(db, b, {"kind": M.DEBT_PAYMENT, "debt_id": debt.id, "counterparty": debt.creditor, "amount_cents": 25000,
                                  "method": "yape", "occurred_at": _dt(d, 10)}, op_id=op(), channel="demo", demo=True, commit=False)
        if rng.random() < 0.35 and not is_today:
            ledger.record(db, b, {"kind": M.EXPENSE, "category": rng.choice(["Movilidad y fletes", "Bolsas y empaques"]),
                                  "expense_type": "variable", "amount_cents": rng.choice([500, 800, 1000, 1500]),
                                  "method": "efectivo", "occurred_at": _dt(d, 18)}, op_id=op(), channel="demo", demo=True, commit=False)
        if rng.random() < 0.45 and not is_today:
            ledger.record(db, b, {"kind": M.WITHDRAWAL, "description": rng.choice(["mercado de la casa", "colegio de los chicos", "pasajes", "medicina"]),
                                  "amount_cents": rng.choice([3000, 5000, 8000, 10000]), "method": rng.choice(["efectivo", "yape"]),
                                  "occurred_at": _dt(d, 20)}, op_id=op(), channel="demo", demo=True, commit=False)
        _rebalance(db, b, d, op)
        if d.weekday() == 5 and d >= goal.created_at.date() and not is_today:
            ledger.record(db, b, {"kind": M.GOAL_SAVING, "goal_id": goal.id, "amount_cents": rng.choice([6000, 8000, 10000]),
                                  "method": "efectivo", "occurred_at": _dt(d, 21)}, op_id=op(), channel="demo", demo=True, commit=False)
        if d == start + timedelta(days=20):
            ledger.record(db, b, {"kind": M.CONTRIBUTION, "amount_cents": 20000, "method": "efectivo",
                                  "description": "plata de mis ahorros", "occurred_at": _dt(d, 9)},
                          op_id=op(), channel="demo", demo=True, commit=False)
        d += timedelta(days=1)
    db.flush()
    _verify_yape(db, b, rng, M.YAPE_OUT_KINDS + ("cobro_fiado",), 0.9)
    # un conteo con diferencia pendiente de revisar (para la demo)
    gorra = prods[3]
    reconcile.stock_count(db, b, gorra, stock[gorra.id] - 1, demo=True, when=_dt(today - timedelta(days=1), 20), commit=False)
    reconcile.cash_count(db, b, "efectivo", ledger.pocket_balances(db, b.id, until=_dt(today, 0))["efectivo"], demo=True,
                         when=_dt(today - timedelta(days=1), 21), commit=False)
    # una venta reciente con adjunto (captura) para mostrar el origen «con adjunto»
    last = db.scalar(select(M.Movement).where(M.Movement.business_id == b.id, M.Movement.kind == M.SALE,
                                              M.Movement.origin == "autodeclarado").order_by(M.Movement.id.desc()))
    if last:
        db.add(M.Attachment(movement_id=last.id, kind="captura_yape", filename="captura-demo.png", demo=True))
        last.origin = "con_adjunto"
    db.commit()
    return b


def seed_food(db: Session, days: int = 60) -> M.Business:
    rng = random.Random(5)
    today = today_lima()
    start = today - timedelta(days=days)
    b = M.Business(name="Cocina de Doña Carmen", owner_name="Carmen", kind="comida", demo=True, setup_state="listo",
                   setup_source="plantilla", description="Vendo menú y jugos al mediodía. Cobro en efectivo y por Yape.",
                   phone="51900000002", created_at=_dt(start, 8))
    db.add(b)
    db.flush()
    for c in TEMPLATES["comida"]["categories"]:
        db.add(M.Category(business_id=b.id, name=c["name"], kind=c["kind"]))
    menu = M.Product(business_id=b.id, name="Menú", aliases=["menu", "menus", "plato", "platos", "almuerzo"], price_cents=1000,
                     cost_cents=600, track_stock=False)
    jugo = M.Product(business_id=b.id, name="Jugo", aliases=["jugos", "juguito"], price_cents=400, cost_cents=150, track_stock=False)
    aceite = M.Product(business_id=b.id, name="Aceite", aliases=["aceite"], is_input=True, unit="litro", cost_cents=900, track_stock=False)
    db.add_all([menu, jugo, aceite])
    db.add_all([M.FixedExpense(business_id=b.id, name="Gas", amount_cents=5500, due_day=3),
                M.FixedExpense(business_id=b.id, name="Alquiler", amount_cents=50000, due_day=1),
                M.FixedExpense(business_id=b.id, name="Sueldos", amount_cents=60000, due_day=30)])
    db.add(M.Asset(business_id=b.id, name="Cocina de 4 hornillas y ollas", value_cents=120000))
    db.flush()
    op = _Op(f"demo-{b.id}")
    ledger.record(db, b, {"kind": M.OPENING, "method": "efectivo", "amount_cents": 40000, "occurred_at": _dt(start, 7)},
                  op_id=op(), channel="demo", demo=True, commit=False)
    ledger.record(db, b, {"kind": M.OPENING, "method": "yape", "amount_cents": 10000, "occurred_at": _dt(start, 7)},
                  op_id=op(), channel="demo", demo=True, commit=False)
    goal = M.Goal(business_id=b.id, kind="ahorro", name="Cocina industrial", target_cents=250000,
                  deadline=today + timedelta(days=90), created_at=_dt(today - timedelta(days=30), 9))
    db.add(goal)
    db.flush()
    d = start
    while d <= today:
        if d.weekday() != 6:
            platos = round(rng.gauss(30, 5) * (0.6 if d.weekday() == 0 else 1))
            jugos = round(platos * 0.4)
            for prod, qty in ((menu, platos), (jugo, jugos)):
                cash_q = round(qty * 0.45)
                for method, q in (("efectivo", cash_q), ("yape", qty - cash_q)):
                    if q <= 0:
                        continue
                    when = _dt(d, 14, rng.randint(0, 59))
                    total = q * prod.price_cents
                    ledger.record(db, b, {"kind": M.SALE, "product_id": prod.id, "quantity": q, "amount_cents": total,
                                          "method": method, "occurred_at": when}, op_id=op(), channel="demo", demo=True, commit=False)
            liters = 3
            price = 900 if (today - d).days >= 7 else 1035
            ledger.record(db, b, {"kind": M.PURCHASE, "product_id": aceite.id, "quantity": liters, "amount_cents": price * liters,
                                  "method": "efectivo", "occurred_at": _dt(d, 7)}, op_id=op(), channel="demo", demo=True, commit=False)
            ledger.record(db, b, {"kind": M.PURCHASE, "category": "Insumos de cocina", "amount_cents": rng.choice([8000, 9000, 10000]),
                                  "method": "yape" if rng.random() < 0.45 else "efectivo", "generic": True, "description": "mercado: pollo, arroz, verduras",
                                  "occurred_at": _dt(d, 6, 30)}, op_id=op(), channel="demo", demo=True, commit=False)
        if d.day == 1:
            ledger.record(db, b, {"kind": M.EXPENSE, "category": "Alquiler", "expense_type": "fijo", "amount_cents": 50000,
                                  "method": "efectivo", "occurred_at": _dt(d, 8)}, op_id=op(), channel="demo", demo=True, commit=False)
        if d.day in (3, 18):
            ledger.record(db, b, {"kind": M.EXPENSE, "category": "Gas", "expense_type": "fijo", "amount_cents": 5500,
                                  "method": "efectivo", "occurred_at": _dt(d, 8)}, op_id=op(), channel="demo", demo=True, commit=False)
        if d.weekday() == 5:
            ledger.record(db, b, {"kind": M.EXPENSE, "category": "Sueldos", "expense_type": "fijo", "amount_cents": 15000,
                                  "method": "efectivo", "occurred_at": _dt(d, 17)}, op_id=op(), channel="demo", demo=True, commit=False)
            if d >= goal.created_at.date():
                ledger.record(db, b, {"kind": M.GOAL_SAVING, "goal_id": goal.id, "amount_cents": 20000, "method": "yape",
                                      "occurred_at": _dt(d, 18)}, op_id=op(), channel="demo", demo=True, commit=False)
        _rebalance(db, b, d, op)
        if rng.random() < 0.6:
            ledger.record(db, b, {"kind": M.WITHDRAWAL, "description": "gastos de la casa", "amount_cents": rng.choice([4000, 6000, 10000]),
                                  "method": "efectivo", "occurred_at": _dt(d, 19)}, op_id=op(), channel="demo", demo=True, commit=False)
        d += timedelta(days=1)
    _verify_yape(db, b, rng, M.YAPE_IN_KINDS + M.YAPE_OUT_KINDS, 0.88)
    db.commit()
    return b


def seed_veg(db: Session, days: int = 75) -> M.Business:
    """Verdulería de mercado: ventas chicas por audio, compras diarias en el mayorista, merma y cierres de caja."""
    from .timeutil import now_lima
    rng = random.Random(23)
    today = today_lima()
    now = now_lima()
    start = today - timedelta(days=days)
    b = M.Business(name="Verdulería Doña Juana", owner_name="Juana", kind="verduras", demo=True, setup_state="listo",
                   setup_source="plantilla", phone="51900000003", created_at=_dt(start, 6),
                   description="Vendo verduras en el mercado. Compro de madrugada en el mayorista y cobro en efectivo y por Yape.")
    db.add(b)
    db.flush()
    for c in TEMPLATES["verduras"]["categories"]:
        db.add(M.Category(business_id=b.id, name=c["name"], kind=c["kind"]))
    prices = {"Tomate": (400, 250), "Papa": (250, 150), "Cebolla": (300, 180), "Limón": (600, 400), "Zanahoria": (250, 140),
              "Ají": (800, 500), "Culantro": (100, 50), "Lechuga": (200, 120), "Choclo": (150, 90), "Ajo": (1200, 800),
              "Zapallo": (300, 180), "Pimiento": (500, 300)}
    from .templates import VEG
    prods = []
    packs = {"Tomate": ("jaba", 20), "Papa": ("saco", 50), "Cebolla": ("saco", 50), "Limón": ("jaba", 15), "Zanahoria": ("saco", 40),
             "Culantro": ("atado", None), "Lechuga": ("unidad", None), "Choclo": ("unidad", None)}
    for n, a, u in VEG:
        pr, co = prices[n]
        unit, eq = packs.get(n, ("kg", None))
        compra = {"unidad": unit, **({"equivale": float(eq), "costo_cents": co * eq} if eq else {"costo_cents": co})}
        spec = {"base": u, "vende_por": [{"unidad": u, "precio_cents": pr}] + ([{"unidad": "soles"}] if u == "kg" else []),
                "compra_por": compra, "creado_por": "demo"}
        tracked = eq is not None
        if tracked:
            spec["stock_inicial"] = {"cantidad": 1, "unidad": unit, "en_base": float(eq)}
        p = M.Product(business_id=b.id, name=n, aliases=a, unit=u, price_cents=pr, cost_cents=co, track_stock=tracked, spec=spec,
                      initial_stock=float(eq) if tracked else None)
        db.add(p)
        prods.append(p)
    db.add_all([M.FixedExpense(business_id=b.id, name="Alquiler del puesto", amount_cents=25000, due_day=1),
                M.FixedExpense(business_id=b.id, name="Luz y agua", amount_cents=3000, due_day=(today + timedelta(days=1)).day)])
    db.add(M.Asset(business_id=b.id, name="Balanza, jabas y carretilla", value_cents=60000))
    goal = M.Goal(business_id=b.id, kind="ahorro", name="Congeladora para conservar verduras", target_cents=120000,
                  deadline=today + timedelta(days=75), created_at=_dt(today - timedelta(days=30), 9))
    db.add(goal)
    db.add(M.Goal(business_id=b.id, kind="reposicion", name="Compra del sábado en el mayorista", target_cents=45000,
                  created_at=_dt(today - timedelta(days=3), 9)))
    db.flush()
    op = _Op(f"demo-{b.id}")
    ledger.record(db, b, {"kind": M.OPENING, "method": "efectivo", "amount_cents": 25000, "occurred_at": _dt(start, 5)},
                  op_id=op(), channel="demo", demo=True, commit=False)
    ledger.record(db, b, {"kind": M.OPENING, "method": "yape", "amount_cents": 5000, "occurred_at": _dt(start, 5)},
                  op_id=op(), channel="demo", demo=True, commit=False)
    weights = [6, 6, 5, 4, 3, 2, 3, 2, 2, 1, 2, 1]
    packed = {p.name: p for p in prods if p.track_stock}
    sold_hist: dict[str, list[float]] = {n: [] for n in packed}
    d = start
    while d <= today:
        is_today = d == today
        f = WD_FACTOR[d.weekday()] * (1.15 if d.weekday() == 6 else 1)
        # compra de madrugada en el mayorista: por jaba/saco lo que se acaba (stock controlado)
        for name, p in packed.items():
            if name == "Papa" and (today - d).days <= 2:
                continue   # para la demo: la papa se está acabando
            avg = (sum(sold_hist[name][-7:]) / max(1, len(sold_hist[name][-7:]))) if sold_hist[name] else 1.5
            stock = ledger.expected_stock(db, p) or 0
            if stock < avg * 2:
                c = p.spec["compra_por"]
                packs_n = max(1, -(-int((avg * 4 - stock) * 10) // int(c["equivale"] * 10)))
                cost = c["costo_cents"] * (1.15 if name == "Tomate" and (today - d).days < 6 else 1)
                ledger.record(db, b, {"kind": M.PURCHASE, "product_id": p.id, "measure": float(packs_n), "measure_unit": c["unidad"],
                                      "amount_cents": int(round(cost * packs_n)), "method": "efectivo", "counterparty": "Mayorista",
                                      "occurred_at": _dt(d, 4, 30)}, op_id=op(), channel="demo", demo=True, commit=False)
        # a veces compra tomate suelto, por kilo, en otro puesto (más caro): base del consejo de ahorro
        if d.weekday() in (2, 5) and not is_today:
            kg = rng.choice([3, 4, 5])
            ledger.record(db, b, {"kind": M.PURCHASE, "product_id": packed["Tomate"].id, "measure": float(kg), "measure_unit": "kg",
                                  "amount_cents": kg * 320, "method": "efectivo", "counterparty": "Puesto del costado",
                                  "occurred_at": _dt(d, 11)}, op_id=op(), channel="demo", demo=True, commit=False)
        if d.weekday() != 0 or rng.random() < 0.5:
            ledger.record(db, b, {"kind": M.PURCHASE, "amount_cents": int(rng.gauss(22000, 2500) * f) // 100 * 100,
                                  "method": "efectivo" if rng.random() < 0.8 else "yape", "generic": True,
                                  "category": "Compra en el mayorista", "description": "verduras del mayorista",
                                  "counterparty": "Mayorista", "occurred_at": _dt(d, 4, 40)},
                          op_id=op(), channel="demo", demo=True, commit=False)
        # ventas del día: unas por producto y otras acumuladas por hora
        last_hour = min(14, now.hour - 1) if is_today else 14
        day_sold: dict[str, float] = {}
        for h in range(7, max(7, last_hour) + 1):
            for _ in range(rng.randint(1, 2)):
                p = rng.choices(prods, weights=weights)[0]
                if p.unit == "kg":
                    kg = rng.choice([0.25, 0.5, 0.5, 1, 1, 1, 1.5, 2])
                    amount = round(p.price_cents * kg / 50) * 50
                    measure, unit, qty = kg, "kg", None
                else:
                    qty = rng.choice([1, 1, 2, 3])
                    amount, measure, unit = p.price_cents * qty, None, None
                ledger.record(db, b, {"kind": M.SALE, "product_id": p.id, "quantity": qty, "measure": measure, "measure_unit": unit,
                                      "amount_cents": amount, "method": "yape" if rng.random() < 0.4 else "efectivo",
                                      "occurred_at": _dt(d, h, rng.randint(0, 59))}, op_id=op(), channel="demo", demo=True, commit=False)
                if p.name in sold_hist:
                    day_sold[p.name] = day_sold.get(p.name, 0) + (measure or qty or 0)
            lump = int(rng.gauss(4200, 1200) * f) // 50 * 50
            if lump > 0:
                ledger.record(db, b, {"kind": M.SALE, "amount_cents": lump, "method": "yape" if rng.random() < 0.35 else "efectivo",
                                      "description": "ventas varias", "category": "Ventas varias", "occurred_at": _dt(d, h, 58)},
                              op_id=op(), channel="demo", demo=True, commit=False)
        if not is_today:
            if rng.random() < 0.3:
                lp = rng.choice([packed["Tomate"], packed["Tomate"], packed["Limón"]])
                kg = rng.choice([1.0, 2.0, 3.0])
                ledger.record(db, b, {"kind": M.LOSS, "product_id": lp.id, "measure": kg, "measure_unit": "kg",
                                      "amount_cents": round(lp.cost_cents * kg), "expense_type": "mercaderia", "category": "malogrado",
                                      "description": f"{lp.name.lower()} malogrado", "occurred_at": _dt(d, 15)},
                              op_id=op(), channel="demo", demo=True, commit=False)
            if rng.random() < 0.6:
                ledger.record(db, b, {"kind": M.EXPENSE, "category": rng.choice(["Bolsas", "Flete y carretilla"]), "expense_type": "variable",
                                      "amount_cents": rng.choice([300, 500, 800, 1000]), "method": "efectivo", "occurred_at": _dt(d, 6)},
                              op_id=op(), channel="demo", demo=True, commit=False)
            ledger.record(db, b, {"kind": M.WITHDRAWAL, "description": rng.choice(["menú de los chicos", "pasajes", "mercado de la casa", "colegio"]),
                                  "amount_cents": rng.choice([4000, 5000, 6000, 8000]), "method": "efectivo", "occurred_at": _dt(d, 16)},
                          op_id=op(), channel="demo", demo=True, commit=False)
            if d.day == 1:
                ledger.record(db, b, {"kind": M.EXPENSE, "category": "Alquiler del puesto", "expense_type": "fijo", "amount_cents": 25000,
                                      "method": "yape", "occurred_at": _dt(d, 7)}, op_id=op(), channel="demo", demo=True, commit=False)
            if d.day == 10:
                ledger.record(db, b, {"kind": M.EXPENSE, "category": "Luz y agua", "expense_type": "fijo", "amount_cents": 3000,
                                      "method": "yape", "occurred_at": _dt(d, 7)}, op_id=op(), channel="demo", demo=True, commit=False)
            if d.weekday() == 5 and d >= goal.created_at.date():
                ledger.record(db, b, {"kind": M.GOAL_SAVING, "goal_id": goal.id, "amount_cents": rng.choice([6000, 8000, 10000]),
                                      "method": "efectivo", "occurred_at": _dt(d, 17)}, op_id=op(), channel="demo", demo=True, commit=False)
            # cierre de caja de la noche (cuadra casi siempre)
            if rng.random() < 0.7:
                bal = ledger.pocket_balances(db, b.id, until=_dt(d, 20))["efectivo"]
                db.add(M.Count(business_id=b.id, kind="caja", pocket="efectivo", counted=bal, expected=bal, difference=0,
                               result="consistente", review_status="revisado", counted_at=_dt(d, 20), demo=True))
        for n2, q2 in day_sold.items():
            sold_hist[n2].append(q2)
        if d == today - timedelta(days=18):
            ledger.record(db, b, {"kind": M.SALE, "amount_cents": 3000, "paid_cents": 0, "counterparty": "Doña Rosa",
                                  "description": "verduras al fiado", "occurred_at": _dt(d, 10)}, op_id=op(), channel="demo", demo=True, commit=False)
        if d == today - timedelta(days=4):
            ledger.record(db, b, {"kind": M.SALE, "amount_cents": 1200, "paid_cents": 0, "counterparty": "Vecina Carmen",
                                  "description": "verduras al fiado", "occurred_at": _dt(d, 11)}, op_id=op(), channel="demo", demo=True, commit=False)
        _rebalance(db, b, d, op)
        bal = ledger.pocket_balances(db, b.id)
        if d.weekday() == 5 and bal["yape"] > 40000 and not is_today:   # retira su Yape en el agente para comprar en el mayorista
            ledger.record(db, b, {"kind": M.TRANSFER, "method": "yape", "to_method": "efectivo", "amount_cents": (bal["yape"] - 15000) // 1000 * 1000,
                                  "occurred_at": _dt(d, 18)}, op_id=op(), channel="demo", demo=True, commit=False)
        d += timedelta(days=1)
    # pedido grande de papa hoy temprano: queda poca (para mostrar la alerta de stock)
    papa = packed["Papa"]
    left = ledger.expected_stock(db, papa) or 0
    if left > 2:
        kg = round(left - 1.5, 2)
        ledger.record(db, b, {"kind": M.SALE, "product_id": papa.id, "measure": kg, "measure_unit": "kg",
                              "amount_cents": round(papa.price_cents * kg * 0.9 / 10) * 10, "method": "yape", "counterparty": "Restaurante El Sabor",
                              "description": "pedido de papa", "occurred_at": min(now - timedelta(minutes=30), _dt(today, 8, 15))},
                      op_id=op(), channel="demo", demo=True, commit=False)
    _verify_yape(db, b, rng, M.YAPE_IN_KINDS + M.YAPE_OUT_KINDS, 0.88)
    db.commit()
    return b


def seed_all(db: Session) -> None:
    if db.scalar(select(M.Business.id).where(M.Business.demo.is_(True))):
        return
    seed_veg(db)
    seed_resale(db)
    seed_food(db)


def reset_demo(db: Session) -> None:
    for b in db.scalars(select(M.Business).where(M.Business.demo.is_(True))).all():
        delete_business(db, b)
    db.commit()
    seed_all(db)


def delete_business(db: Session, b: M.Business) -> None:
    bid = b.id
    for model in (M.CashEntry, M.StockEntry, M.YapePayment, M.Count, M.Draft, M.ChatLog, M.ReportConsent,
                  M.FixedExpense, M.Asset, M.Category, M.Notification):
        for row in db.scalars(select(model).where(model.business_id == bid)).all():
            db.delete(row)
    db.flush()
    mids = db.scalars(select(M.Movement.id).where(M.Movement.business_id == bid)).all()
    for model in (M.MovementRevision, M.Attachment):
        for row in db.scalars(select(model).where(model.movement_id.in_(mids))).all():
            db.delete(row)
    db.flush()
    for mv in db.scalars(select(M.Movement).where(M.Movement.business_id == bid)).all():
        mv.parent_id = None
    db.flush()
    for model in (M.Movement,):
        for row in db.scalars(select(model).where(model.business_id == bid)).all():
            db.delete(row)
    db.flush()
    for model in (M.Goal, M.Debt):
        for row in db.scalars(select(model).where(model.business_id == bid)).all():
            db.delete(row)
    for row in db.scalars(select(M.ProcessedMessage).where(M.ProcessedMessage.business_id == bid)).all():
        db.delete(row)
    for row in db.scalars(select(M.Product).where(M.Product.business_id == bid)).all():
        db.delete(row)
    db.flush()
    db.delete(b)
    db.flush()


__all__ = ["seed_all", "reset_demo", "add_months", "month_start"]
