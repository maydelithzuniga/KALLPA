"""Casos de aceptación del MVP (sección «Entrega y criterios de aceptación»)."""
import pytest
import io

from app import transcribe


def dash(client, bid):
    return client.get(f"/api/businesses/{bid}/dashboard").json()


def stock(client, bid, pid):
    return next(i for i in client.get(f"/api/businesses/{bid}/inventory").json() if i["id"] == pid)["expected_stock"]


# 1 ---------------------------------------------------------------------------
def test_1_crear_negocio_por_conversacion_y_por_plantilla_sin_credenciales(client):
    b = client.post("/api/businesses", json={"name": "Mi negocio"}).json()
    r = client.post(f"/api/businesses/{b['id']}/setup/propose",
                    json={"description": "Vendo polos y shorts, compro por docena y cobro por Yape y en efectivo"}).json()
    assert r["proposal"]["kind"] == "reventa"
    assert r["proposal"]["source"] == "plantilla"           # Gemini desactivado -> plantilla local
    names = [p["name"].lower() for p in r["proposal"]["products"]]
    assert "polo" in names and "short" in names
    assert all(p.get("price_cents") is None for p in r["proposal"]["products"])  # precios desconocidos
    ok = client.post(f"/api/businesses/{b['id']}/setup/confirm", json={}).json()
    assert ok["setup_state"] == "listo"
    inv = client.get(f"/api/businesses/{b['id']}/inventory").json()
    assert all(i["price_cents"] is None and i["initial_stock"] is None for i in inv)

    b2 = client.post("/api/businesses", json={"name": "Otro"}).json()
    ok2 = client.post(f"/api/businesses/{b2['id']}/setup/template", json={"kind": "reventa"}).json()
    assert ok2["setup_state"] == "listo" and ok2["setup_source"] == "plantilla"
    for kind in ("comida", "servicios"):
        b3 = client.post("/api/businesses", json={"name": kind}).json()
        assert client.post(f"/api/businesses/{b3['id']}/setup/template", json={"kind": kind}).json()["kind"] == kind


def test_1b_inventario_armado_por_conversacion(client):
    """La primera conversación arma el inventario (ficha JSON por producto) y recién después acepta ventas."""
    b = client.post("/api/businesses", json={}).json()
    n = [0]

    def c(t):
        n[0] += 1
        return client.post(f"/api/businesses/{b['id']}/chat", json={"text": t, "message_id": f"s{n[0]}"}).json()
    assert "¿Cómo te llamas?" in c("hola")["reply"]
    assert "¿Qué vendes?" in c("me llamo Juana")["reply"]
    r = c("vendí 3 soles de tomate")            # todavía no registra ventas
    assert "Anoto tus ventas apenas terminemos" in r["reply"]
    assert "Anoté: tomate, papa, cebolla, limón" in c("vendo verduras: tomate, papa, cebolla y limón")["reply"]
    assert "culantro" in c("también culantro")["reply"]
    assert "¿Cómo vendes" in c("eso es todo")["reply"]
    assert "kilo de tomate" in c("por kilo, pero el culantro por atado")["reply"]
    c("a 4, me cuesta 2.50")
    c("a 2.50 y me cuesta 1.50")
    c("3")
    c("no sé")
    c("6 y me cuesta 4")
    assert "mayorista" in c("a 1, me cuesta 0.50")["reply"]
    assert "cuántos kilos trae la saco de papa" in c("el tomate por jaba de 20 kilos a 50 soles, la papa por saco a 80 soles")["reply"]
    c("50")
    assert "¿Cómo te pagan" in c("2 jabas de tomate, medio saco de papa y 5 kilos de cebolla")["reply"]
    assert "¿qué cosas pagas para tu negocio y cada cuánto?" in c("las dos")["reply"]
    r = c("alquiler del puesto 250 al mes, pasaje 5 al día y bolsas 10 a la semana")["reply"]
    assert "• Alquiler del puesto S/ 250 al mes (fijo)" in r and "• Pasaje S/ 5 al día (fijo)" in r
    assert "• Bolsas S/ 10 a la semana (variable)" in r and "S/ 400 fijos" in r
    assert "¿Cada cuánto pagas licencia" in c("la licencia 120")["reply"]
    assert "Licencia S/ 120 al año (fijo)" in c("al año")["reply"]
    assert "cuenta la plata" in c("eso es todo")["reply"]
    r = c("150 en efectivo y 40 en yape")
    assert "Así quedó tu negocio" in r["reply"] and r["setup"]["stage"] == "resumen"
    assert "S/ 3.50" in c("el tomate es a 3.50")["reply"]
    r = c("sí")
    assert r["setup"]["done"] is True
    assert client.get(f"/api/businesses/{b['id']}").json()["setup_state"] == "listo"
    fx = {f["name"]: f for f in client.get(f"/api/businesses/{b['id']}/fixed-expenses").json()}
    assert fx["Pasaje"]["frequency"] == "diario" and fx["Pasaje"]["monthly_cents"] == 15000
    assert fx["Bolsas"]["cost_type"] == "variable" and fx["Licencia"]["frequency"] == "anual"
    be = client.get(f"/api/businesses/{b['id']}/dashboard").json()
    assert be["break_even"]["fixed_cents"] == 25000 + 15000 + 1000   # alquiler + pasaje×30 + licencia/12
    inv = {i["name"]: i for i in client.get(f"/api/businesses/{b['id']}/inventory").json()}
    tom = inv["Tomate"]
    assert tom["spec"]["compra_por"] == {"unidad": "jaba", "equivale": 20.0, "costo_cents": 5000}
    assert tom["spec"]["stock_inicial"]["en_base"] == 40 and tom["expected_stock"] == 40 and tom["price_cents"] == 350
    assert inv["Papa"]["expected_stock"] == 25 and inv["Culantro"]["unit"] == "atado"
    # ya acepta ventas: una jaba se cobra a 20 kg × S/ 3.50
    r = c("vendí una jaba de tomate en efectivo")
    assert r["reply"].startswith("✓ S/ 70 tomate (1 jaba)")
    c("vendí 3 soles de papa en efectivo")      # 1.2 kg estimados con el precio por kilo
    inv = {i["name"]: i for i in client.get(f"/api/businesses/{b['id']}/inventory").json()}
    assert inv["Papa"]["expected_stock"] == 23.8 and inv["Tomate"]["expected_stock"] == 20


# 2 ---------------------------------------------------------------------------
# 2 ---------------------------------------------------------------------------
def test_2_venta_con_descuento_se_guarda_al_toque_e_idempotente(client, shop, chat):
    bid, pid = shop["id"], shop["pid"]
    before = dash(client, bid)["cash"]
    r = chat("Vendí tres polos por cincuenta soles en efectivo", message_id="audio-1")
    assert r["reply"].startswith("✓ S/ 50 tres polos · efectivo · desc. S/ 10")
    mv = r["movement"]
    assert mv["discount_cents"] == 1000 and mv["amount_cents"] == 5000 and mv["unit_price_ref_cents"] == 2000
    assert dash(client, bid)["cash"]["efectivo_cents"] == before["efectivo_cents"] + 5000
    assert stock(client, bid, pid) == 7
    # reenviar el mismo audio no duplica
    assert chat("Vendí tres polos por cincuenta soles en efectivo", message_id="audio-1")["duplicate"] is True
    assert dash(client, bid)["cash"]["efectivo_cents"] == before["efectivo_cents"] + 5000
    assert stock(client, bid, pid) == 7
    assert len(client.get(f"/api/businesses/{bid}/movements?kind=venta").json()) == 1


def test_2b_audio_real_pasa_por_transcripcion_una_sola_vez(client, shop, monkeypatch):
    bid = shop["id"]
    calls = []

    def fake(data, suffix):
        calls.append(data)
        return "Vendí tres polos por cincuenta soles en efectivo"

    monkeypatch.setattr(transcribe, "transcribe_bytes", fake)
    post = lambda mid: client.post(f"/api/businesses/{bid}/chat/audio",
                                   files={"audio": ("a.webm", io.BytesIO(b"fake-audio"), "audio/webm")},
                                   data={"message_id": mid}).json()
    r = post("rec-1")
    assert r["transcript"].startswith("Vendí tres polos")
    assert r["movement"]["amount_cents"] == 5000
    assert post("rec-1")["duplicate"] is True
    assert len(calls) == 1


def test_2c_solo_pregunta_lo_que_falta(client, shop, chat):
    r = chat("vendí tres polos a S/60")          # polo a S/ 20: 3 × 20 = 60, es el total (no pregunta)
    assert "¿En efectivo o por Yape?" in r["reply"]
    r = chat("en efectivo")
    assert r["movement"]["amount_cents"] == 6000 and r["movement"]["discount_cents"] == 0
    r = chat("vendí 3 polos a 35")               # ni 20 c/u ni 60 en total: ahí sí pregunta
    assert "total o el precio de cada uno" in r["reply"]
    chat("cancelar")
    r = chat("vendí 2 polos a 25 cada uno por yape")
    assert r["movement"]["amount_cents"] == 5000 and r["movement"]["discount_cents"] == 0
    r = chat("vendí 2 polos por 40 por yape y por 30")
    assert "dos montos" in r["reply"]


def test_2d_fiado_parcial_y_cobro_vinculado(client, shop, chat):
    bid = shop["id"]
    base = dash(client, bid)["cash"]["efectivo_cents"]
    sale = chat("vendí 2 polos por 40 a la señora Juana, me pagó 30 y me debe 10 en efectivo")["movement"]
    assert sale["paid_cents"] == 3000 and sale["pending_cents"] == 1000
    assert dash(client, bid)["cash"]["efectivo_cents"] == base + 3000
    r = chat("Juana me pagó 10 del fiado en efectivo")
    assert r["movement"]["parent_id"] == sale["id"] and "ya no te debe nada" in r["reply"]
    assert dash(client, bid)["receivables"] == []


def test_2e_deshacer_y_corregir(client, shop, chat):
    bid, pid = shop["id"], shop["pid"]
    mv = chat("Vendí tres polos por cincuenta soles en efectivo")["movement"]
    r = chat("corrige: eran dos polos")
    assert r["reply"].startswith("Corregido")
    m = client.get(f"/api/movements/{mv['id']}").json()
    assert m["quantity"] == 2 and m["revision"] == 2 and len(m["revisions"]) == 1
    assert stock(client, bid, pid) == 8
    r = chat("deshacer")
    assert r["reply"].startswith("Listo, lo borré")
    assert stock(client, bid, pid) == 10
    assert client.get(f"/api/movements/{mv['id']}").json()["status"] == "anulado"


# 3 ---------------------------------------------------------------------------
def test_3_compra_por_docena(client, shop, chat):
    bid, pid = shop["id"], shop["pid"]
    yape0 = dash(client, bid)["cash"]["yape_cents"]
    mv = chat("Compré una docena de polos por S/144 en total y pagué por Yape")["movement"]
    assert mv["quantity"] == 12 and mv["amount_cents"] == 14400 and mv["unit_cost_cents"] == 1200
    assert stock(client, bid, pid) == 22
    assert dash(client, bid)["cash"]["yape_cents"] == yape0 - 14400
    mv = chat("compré mercadería por 144 en efectivo")["movement"]
    assert mv["units_pending"] is True and mv["quantity"] is None


# 4 ---------------------------------------------------------------------------
def test_4_conciliacion_de_stock_y_reporte(client, shop, chat):
    bid, pid = shop["id"], shop["pid"]
    chat("Compré una docena de polos por S/144 en total y pagué por Yape")
    chat("Vendí tres polos por cincuenta soles en efectivo")
    assert stock(client, bid, pid) == 19
    r = chat("conté 17 polos")
    assert "faltan 2" in r["reply"]
    assert r["count"]["expected"] == 19 and r["count"]["difference"] == -2 and r["count"]["result"] == "diferencia"
    client.post(f"/api/counts/{r['count']['id']}/resolve", json={"action": "pendiente"})
    rep = client.get(f"/api/businesses/{bid}/report/full").json()
    sale = next(m for m in rep["movements"] if m["kind"] == "venta")
    assert sale["amount_cents"] == 5000 and sale["discount_cents"] == 1000 and sale["reference_total_cents"] == 6000
    assert sale["check"] == "Con diferencia"
    assert rep["reconciliation"]["open"][0]["difference"] == -2


def test_4b_conteo_de_caja(client, shop, chat):
    r = chat("tengo 90 en efectivo en caja")
    assert r["count"]["expected"] == 10000 and r["count"]["difference"] == -1000


# 5 ---------------------------------------------------------------------------
def test_5_aportes_y_traslados_no_inflan_ventas(client, shop, chat):
    bid = shop["id"]
    d0 = dash(client, bid)
    assert chat("puse 200 de mi bolsillo al negocio en efectivo")["movement"]["kind"] == "aporte"
    assert chat("pasé 100 de yape a efectivo")["movement"]["kind"] == "traslado"
    assert chat("me saqué 50 para la casa en efectivo")["movement"]["kind"] == "retiro_personal"
    d1 = dash(client, bid)
    assert d1["day"]["sales_cents"] == 0 and d1["day"]["contributions_cents"] == 20000
    assert d1["day"]["withdrawals_cents"] == 5000 and d1["day"]["expenses_cents"] == 0
    assert d1["cash"]["efectivo_cents"] == d0["cash"]["efectivo_cents"] + 20000 + 10000 - 5000
    assert d1["cash"]["yape_cents"] == d0["cash"]["yape_cents"] - 10000


def test_5b_audio_pendiente_se_procesa_una_vez(client, shop, monkeypatch):
    bid = shop["id"]
    monkeypatch.setattr(transcribe, "transcribe_bytes", lambda d, s: "gasté 40 en pasajes en efectivo")
    e0 = dash(client, bid)["cash"]["efectivo_cents"]
    send = lambda mid: client.post(f"/api/businesses/{bid}/chat/audio",
                                   files={"audio": ("p.webm", io.BytesIO(b"x"), "audio/webm")},
                                   data={"message_id": mid, "recorded_at": "2026-11-06T10:00:00-05:00"}).json()
    r = send("offline-1")
    assert r["movement"]["occurred_at"].startswith("2026-11-06T10:00")
    send("offline-1")
    send("offline-1")
    assert dash(client, bid)["cash"]["efectivo_cents"] == e0 - 4000


# 6 ---------------------------------------------------------------------------
def test_6_meta_de_reposicion_y_reporte_coincide(client, shop, chat):
    bid = shop["id"]
    client.post(f"/api/businesses/{bid}/fixed-expenses", json={"name": "Luz", "amount_cents": 5000, "due_day": 28})
    g = client.post(f"/api/businesses/{bid}/goals", json={"kind": "reposicion", "name": "Reponer polos", "target_cents": 20000}).json()
    assert "Tu próxima compra cuesta S/ 200" in g["message"]
    chat("Vendí tres polos por cincuenta soles en efectivo")
    chat("pagué la luz 30 en efectivo")
    d = dash(client, bid)
    goal = next(x for x in d["goals"] if x["kind"] == "reposicion")
    assert goal["available_cents"] == d["cash"]["total_cents"] - d["cash"]["upcoming_total_cents"]
    rep = client.get(f"/api/businesses/{bid}/report/full").json()
    assert rep["summary"]["sales_cents"] == 5000 and rep["summary"]["expenses_cents"] == 3000


def test_catalogo_cuesta_ambiguo(client, shop, chat):
    r = chat("Mi polo cuesta S/20 y tengo diez en stock")
    assert "precio al que lo vendes o lo que te cuesta" in r["reply"]
    r = chat("me cuesta eso")
    assert r["reply"].startswith("Listo, actualicé")


def test_meta_de_ahorro_por_chat(client, shop, chat):
    r = chat("quiero juntar 1500 para una congeladora en 10 semanas")
    assert "Meta guardada" in r["reply"]
    r = chat("separé 30 para la congeladora en efectivo")
    assert "vas al 2%" in r["reply"]


def test_explicacion_flujo_de_caja(client, shop, chat):
    chat("Vendí tres polos por cincuenta soles en efectivo")
    r = chat("¿Qué es eso del flujo de caja?")
    assert r["reply"].startswith("Es la plata que de verdad tienes en la mano para usar")


# 7 ---------------------------------------------------------------------------
def test_7_informe_bcp_solo_yape_verificado(client, shop, chat):
    bid = shop["id"]
    chat("Vendí tres polos por cincuenta soles en efectivo")
    venta_yape = chat("vendí un polo en 20 por yape")
    assert "Yape (por verificar)" in venta_yape["reply"]
    gasto_yape = chat("pagué la luz 30 por yape")["movement"]
    sin_verificar = chat("vendí un polo en 25 por yape")["movement"]
    rep = client.get(f"/api/businesses/{bid}/report").json()
    assert rep["totals"]["operations"] == 0 and rep["verification"]["pending"] == 3
    assert client.post(f"/api/businesses/{bid}/yape/demo", json={"payer": "Lucía", "amount_cents": 2000}).json()["linked_movement_id"] == venta_yape["movement"]["id"]
    assert client.post(f"/api/businesses/{bid}/yape/demo", json={"payer": "Enel", "amount_cents": 3000, "movement_id": gasto_yape["id"]}).json()["direction"] == "salida"
    rep = client.get(f"/api/businesses/{bid}/report").json()
    assert rep["totals"]["income_cents"] == 2000 and rep["totals"]["out_cents"] == 3000
    assert rep["totals"]["operations"] == 2 and rep["verification"]["pending"] == 1
    assert sin_verificar["id"] not in [m["id"] for m in rep["movements"]]


# 8 ---------------------------------------------------------------------------
@pytest.fixture()
def veg(client):
    b = client.post("/api/businesses", json={"name": "Verdulería", "owner_name": "Juana"}).json()
    client.post(f"/api/businesses/{b['id']}/setup/template", json={"kind": "verduras"})
    ids = {i["name"]: i["id"] for i in client.get(f"/api/businesses/{b['id']}/inventory").json()}
    client.patch(f"/api/products/{ids['Papa']}", json={"price_cents": 250, "cost_cents": 150})
    client.post(f"/api/businesses/{b['id']}/opening", json={"efectivo_cents": 10000, "yape_cents": 0})
    return b["id"]


def test_8_varias_ventas_en_un_audio_y_acumulado(client, veg):
    from tests.conftest import Chat
    chat = Chat(client, veg)
    r = chat("vendí 3 soles de tomate y un kilo de papa en efectivo")
    assert r["reply"] == "✓ S/ 3 tomate, S/ 2.50 papa (1 kg) · efectivo"
    r = chat("vendí tomate, cebolla y limón, todo 12 soles")
    assert r["reply"] == "¿Te pagaron en efectivo o por Yape?"
    r = chat("yape")
    assert r["reply"] == "✓ S/ 12 tomate, cebolla y limón · Yape (por verificar)"
    r = chat("en esta última hora vendí como 60 en efectivo")
    assert r["reply"] == "✓ S/ 60 ventas varias · efectivo"
    r = chat("vendí medio kilo de limón en efectivo")
    assert r["reply"] == "¿Cuánto cobraste por ½ kg de limón?"
    assert chat("4")["reply"] == "✓ S/ 4 limón (½ kg) · efectivo"
    assert chat("deshacer")["reply"] == "Listo, lo borré: S/ 4 limón (½ kg)."
    d = dash(client, veg)
    assert d["day"]["sales_cents"] == 300 + 250 + 1200 + 6000
    assert d["cash"]["efectivo_cents"] == 10000 + 300 + 250 + 6000


def test_9_cierre_del_dia_sobrante_y_merma(client, veg):
    from tests.conftest import Chat
    chat = Chat(client, veg)
    chat("vendí 5 soles de papa en efectivo")                   # efectivo esperado: 100 + 5 = 105
    r = chat("cerrar mi día")
    assert "cuenta la plata de tu monedero" in r["reply"]
    r = chat("tengo 135")
    assert "te sobran S/ 30" in r["reply"]
    r = chat("sí, guárdalas")
    assert "Guardé S/ 30 como ventas en efectivo" in r["reply"] and "¿Tuviste alguna pérdida hoy?" in r["reply"]
    r = chat("media jaba de tomate")
    assert r["reply"] == "¿Cuánto valía eso, más o menos?"
    r = chat("30")
    assert "Anoté la pérdida: S/ 30" in r["reply"] and "tu día está cerrado" in r["reply"]
    d = dash(client, veg)
    assert d["day"]["sales_cents"] == 3500 and d["cash"]["efectivo_cents"] == 13500
    assert d["day"]["loss_cents"] == 3000


def test_9b_cierre_faltante_para_la_casa(client, veg):
    from tests.conftest import Chat
    chat = Chat(client, veg)
    chat("cerrar mi día")
    r = chat("tengo 80")
    assert "te faltan S/ 20" in r["reply"]
    r = chat("fue para la casa")
    assert "para la casa" in r["reply"]
    assert chat("no")["reply"].startswith("Listo, tu día está cerrado")
    assert dash(client, veg)["day"]["withdrawals_cents"] == 2000


# 10 --------------------------------------------------------------------------
def test_10_perdidas_de_cualquier_tipo(client, shop, chat):
    bid, pid = shop["id"], shop["pid"]
    e0 = dash(client, bid)["cash"]["efectivo_cents"]
    r = chat("se mancharon 2 polos")                 # mercadería con stock: se valora al costo (2 × S/ 12)
    assert r["reply"].startswith("✓ pérdida S/ 24")
    assert stock(client, bid, pid) == 8
    r = chat("me robaron 50 soles")
    assert r["reply"] == "¿Era plata del efectivo o del Yape?"
    r = chat("efectivo")
    assert "pérdida S/ 50" in r["reply"]
    assert dash(client, bid)["cash"]["efectivo_cents"] == e0 - 5000
    r = chat("se me rompió la balanza")
    assert r["reply"] == "¿Cuánto valía eso, más o menos?"
    assert "pérdida S/ 120" in chat("120")["reply"]
    d = dash(client, bid)["day"]
    assert d["loss_cents"] == 2400 + 5000 + 12000 and d["profit_cents"] == -(2400 + 5000 + 12000)
    assert d["sales_cents"] == 0
    chat("deshacer")
    assert dash(client, bid)["day"]["loss_cents"] == 2400 + 5000


# 11 --------------------------------------------------------------------------
def test_11_contar_plata_en_vez_de_saldo_inicial(client):
    from tests.conftest import Chat
    b = client.post("/api/businesses", json={"name": "x"}).json()
    client.post(f"/api/businesses/{b['id']}/setup/template", json={"kind": "verduras"})
    chat = Chat(client, b["id"])
    assert chat("quiero contar mi plata")["reply"] == "Cuenta la plata que tienes ahora en tu monedero. ¿Cuánto es?"
    r = chat("tengo 180")
    assert "tienes S/ 180 en efectivo" in r["reply"]
    assert dash(client, b["id"])["cash"]["efectivo_cents"] == 18000


def test_12_lista_de_cobros_para_la_vendedora(client, shop, chat):
    bid = shop["id"]
    chat("vendí 2 polos por 40 a la señora Juana, me pagó 30 y me debe 10 en efectivo")
    r = chat("¿quién me debe?")
    assert r["reply"] == "Por cobrar (S/ 10): Juana S/ 10, de hoy." and not r.get("share")
    # la lista va a ELLA al final del día, de la semana y del mes (nunca a la casera)
    noche = client.post(f"/api/businesses/{bid}/notifications/run?slot=noche").json()
    assert noche[0]["text"].startswith("Hoy vendiste S/ 40") and "Por cobrar (S/ 10): Juana" in noche[0]["text"]
    semana = client.post(f"/api/businesses/{bid}/notifications/run?slot=semana").json()
    assert semana[0]["text"].startswith("Tu semana:") and "Por cobrar (S/ 10)" in semana[0]["text"]
    mes = client.post(f"/api/businesses/{bid}/notifications/run?slot=mes").json()
    assert "Tu informe para el BCP está listo" in mes[0]["text"] and "Por cobrar (S/ 10)" in mes[0]["text"]
    hist = client.get(f"/api/businesses/{bid}/chat/history").json()
    assert sum(1 for h in hist if h["channel"] == "aviso") == 3


def test_13_maximo_dos_mensajes_al_dia(client, shop, chat):
    from datetime import datetime
    from app import notify, models as M
    from app.db import SessionLocal
    chat("vendí 2 polos por 40 a la señora Juana, me pagó 30 y me debe 10 en efectivo")
    with SessionLocal() as db:
        b = db.get(M.Business, shop["id"])
        day = datetime(2026, 11, 4, 20, 0)          # miércoles 8 p. m.
        first = notify.run(db, b, now=day)
        again = notify.run(db, b, now=day.replace(hour=21))
        assert len(first) <= 2 and again == []


def test_14_consejo_comprar_por_jaba(client):
    from tests.conftest import Chat
    b = client.post("/api/businesses", json={"name": "v"}).json()
    client.post(f"/api/businesses/{b['id']}/setup/template", json={"kind": "verduras"})
    ids = {i["name"]: i["id"] for i in client.get(f"/api/businesses/{b['id']}/inventory").json()}
    from app import models as M
    from app.db import SessionLocal
    with SessionLocal() as db:
        p = db.get(M.Product, ids["Tomate"])
        p.spec = {"base": "kg", "vende_por": [{"unidad": "kg", "precio_cents": 400}], "compra_por": {"unidad": "jaba", "equivale": 20.0, "costo_cents": 5000}}
        db.commit()
    chat = Chat(client, b["id"])
    for _ in range(4):
        chat("compré 5 kilos de tomate a 16 en efectivo")
    tips = dash(client, b["id"])["advice"]
    assert any(t.startswith("Si compras el tomate por jaba y no por kilo, ahorras") for t in tips)



# 15 --------------------------------------------------------------------------
@pytest.fixture()
def fake_agent(monkeypatch):
    """Simula a Gemini (el agente de Women2) sin red: devuelve la intención como lo haría el modelo."""
    from app import agent
    from app.config import settings
    monkeypatch.setattr(settings, "agent_enabled", True)
    monkeypatch.setattr(settings, "gemini_api_key", "test")
    answers = {
        "audio-venta": {"transcripcion": "vendí dos polos a cuarenta soles por yape",
                        "intent": {"tipo": "venta", "items": [{"producto": "polo", "cantidad": 2, "unidad": "unidad", "monto": 40}], "metodo_pago": "yape"},
                        "respuesta_voz": "¡Bien! Registré tu venta."},
        "gasté quince en pasajes": {"transcripcion": "gasté quince en pasajes",
                                   "intent": {"tipo": "gasto", "monto": 15, "metodo_pago": None, "descripcion": "pasajes"}, "respuesta_voz": ""},
        "¿me conviene abrir los domingos?": {"transcripcion": "¿me conviene abrir los domingos?", "intent": {"tipo": "consulta"},
                               "respuesta_voz": "Vas muy bien, Ana: este mes llevas S/ 40 en ventas."},
    }
    calls = []

    def analyze(db, b, *, text=None, audio=None, mime_type="audio/ogg", timeout=30.0):
        calls.append(text or "audio")
        return answers["audio-venta" if audio is not None else text]
    monkeypatch.setattr(agent, "analyze", analyze)

    def transcribe_audio(audio, mime_type="audio/ogg", timeout=9.0):
        calls.append("audio")
        return answers["audio-venta"]["transcripcion"]
    monkeypatch.setattr(agent, "transcribe_audio", transcribe_audio)
    return calls


def test_15_agente_en_chat_de_la_app_texto_y_audio(client, shop, fake_agent):
    bid = shop["id"]
    r = client.post(f"/api/businesses/{bid}/chat/audio", files={"audio": ("a.webm", io.BytesIO(b"x"), "audio/webm")},
                    data={"message_id": "ag-1"}).json()
    assert r["transcript"] == "vendí dos polos a cuarenta soles por yape"   # Gemini solo transcribe; las reglas entienden
    assert r["reply"].startswith("✓ S/ 40 polo (2)") or r["movement"]["amount_cents"] == 4000
    r = client.post(f"/api/businesses/{bid}/chat", json={"text": "gasté quince en pasajes", "message_id": "ag-2"}).json()
    assert r["reply"] == "Gasto del negocio: movilidad y fletes, S/ 15. ¿Salió del efectivo o del Yape?"
    r = client.post(f"/api/businesses/{bid}/chat", json={"text": "efectivo", "message_id": "ag-3"}).json()   # pregunta abierta: sin IA
    assert r["movement"]["amount_cents"] == 1500 and fake_agent == ["audio"]   # lo escrito que entienden las reglas no usa IA
    r = client.post(f"/api/businesses/{bid}/chat", json={"text": "¿me conviene abrir los domingos?", "message_id": "ag-4"}).json()
    assert r["reply"].startswith("Vas muy bien")


def test_16_agente_por_whatsapp_texto_y_audio(client, fake_agent, monkeypatch):
    from app import main, whatsapp
    from app.config import settings
    from app.db import SessionLocal
    from app import models as M
    monkeypatch.setattr(settings, "whatsapp_enabled", True)
    sent = []
    monkeypatch.setattr(whatsapp, "send_text", lambda to, body, quick=None: sent.append(body))
    monkeypatch.setattr(whatsapp, "download_media", lambda media_id: b"ogg-bytes")
    monkeypatch.setattr(whatsapp, "send_voice_reply", lambda to, text, mid: sent.append("[voz] " + text))
    with SessionLocal() as db:
        b = M.Business(name="Tienda WA", phone="51999111222", setup_state="listo", kind="reventa")
        db.add(b)
        db.flush()
        db.add(M.Product(business_id=b.id, name="Polo", aliases=["polo", "polos"], price_cents=2000, cost_cents=1200, initial_stock=10))
        db.commit()
        bid = b.id
    main._wa_process([{"id": "wamid.1", "from": "51999111222", "type": "audio", "media_id": "m1", "timestamp": None}])
    main._wa_process([{"id": "wamid.1", "from": "51999111222", "type": "audio", "media_id": "m1", "timestamp": None}])  # reintento de Meta
    main._wa_process([{"id": "wamid.2", "from": "51999111222", "type": "text", "text": "gasté quince en pasajes", "timestamp": None}])
    main._wa_process([{"id": "wamid.3", "from": "51999111222", "type": "text", "text": "yape", "timestamp": None}])
    assert sent[0].startswith("🎙️ «vendí dos polos a cuarenta soles por yape»") and "S/ 40" in sent[0]
    assert sent[1].startswith("[voz]")
    assert "¿Salió del efectivo o del Yape?" in sent[2] and "S/ 15" in sent[3]
    d = client.get(f"/api/businesses/{bid}/dashboard").json()
    assert d["day"]["sales_cents"] == 4000 and d["day"]["expenses_cents"] == 1500   # la app ve lo mismo


def test_28_whatsapp_por_twilio_sandbox(client, monkeypatch):
    """WhatsApp por Twilio: firma válida, texto y audio, respuestas por la API de Twilio, sin duplicar reintentos."""
    from app import twilio_wa
    from app.config import settings
    from app.db import SessionLocal
    from app import models as M
    for k, v in {"whatsapp_enabled": True, "whatsapp_provider": "twilio", "twilio_account_sid": "ACtest",
                 "twilio_auth_token": "secreto", "twilio_validate": True, "app_base_url": "https://kallpa.test"}.items():
        monkeypatch.setattr(settings, k, v)
    sent = []
    import httpx
    monkeypatch.setattr(httpx, "post", lambda *a, **k: sent.append(a) or (_ for _ in ()).throw(AssertionError("REST no")))
    with SessionLocal() as db:
        b = M.Business(name="Verdulería", phone="51919142871", setup_state="listo", kind="reventa")
        db.add(b)
        db.flush()
        db.add(M.Product(business_id=b.id, name="Polo", aliases=["polo", "polos"], price_cents=2000, cost_cents=1200, initial_stock=10))
        db.commit()
        bid = b.id

    def post(form, sign=True):
        sig = twilio_wa.signature_for("https://kallpa.test/webhook/twilio", form) if sign else "malo"
        return client.post("/webhook/twilio", data=form, headers={"X-Twilio-Signature": sig})

    form = {"MessageSid": "SM1", "From": "whatsapp:+51919142871", "To": "whatsapp:+14155238886",
            "Body": "vendí un polo a 20 soles en efectivo", "NumMedia": "0"}
    assert post(form, sign=False).status_code == 401
    r = post(form)
    assert r.status_code == 200 and "<Message><Body>" in r.text and "S/ 20" in r.text   # respuesta en línea (TwiML)
    assert "<Message>" not in post(form).text   # reintento de Twilio: no se duplica
    assert sent == []   # no usa la API REST (que exige KYC aprobado)
    d = client.get(f"/api/businesses/{bid}/dashboard").json()
    assert d["day"]["sales_cents"] == 2000
    h = client.get("/api/health").json()["whatsapp"]
    assert h["connected"] and h["provider"] == "twilio" and h["number"] == "14155238886"


def test_29_whatsapp_por_puente_gratis(client, monkeypatch):
    """Puente (bridge/): clave obligatoria, texto y audio, respuestas y avisos salen por la bandeja del puente."""
    import base64
    from app import notify, whatsapp
    from app.config import settings
    from app.db import SessionLocal
    from app import models as M
    for k, v in {"whatsapp_enabled": True, "whatsapp_provider": "bridge", "bridge_secret": "clave123"}.items():
        monkeypatch.setattr(settings, k, v)
    whatsapp.bridge_drain()
    with SessionLocal() as db:
        b = M.Business(name="Bodega", phone="51919142871", setup_state="listo", kind="reventa")
        db.add(b)
        db.flush()
        db.add(M.Product(business_id=b.id, name="Polo", aliases=["polo", "polos"], price_cents=2000, cost_cents=1200, initial_stock=10))
        db.commit()
        bid = b.id
    h = {"X-Bridge-Secret": "clave123"}
    msg = {"id": "ABC1", "from": "51919142871", "text": "vendí un polo a 20 soles en efectivo"}
    assert client.post("/webhook/bridge", json=msg, headers={"X-Bridge-Secret": "mala"}).status_code == 401
    out = client.post("/webhook/bridge", json=msg, headers=h).json()["outbox"]
    assert len(out) == 1 and out[0]["to"] == "51919142871" and "S/ 20" in out[0]["text"]
    assert client.post("/webhook/bridge", json=msg, headers=h).json()["outbox"] == []   # reintento: sin duplicar
    assert client.get(f"/api/businesses/{bid}/dashboard").json()["day"]["sales_cents"] == 2000
    # audio: llega como base64; sin voz en el servidor responde que no pudo escuchar
    monkeypatch.setattr(settings, "agent_voice_reply", False)
    out = client.post("/webhook/bridge", json={"id": "ABC2", "from": "51919142871", "audio_b64": base64.b64encode(b"x").decode(),
                                               "mime": "audio/ogg"}, headers=h).json()["outbox"]
    assert len(out) == 1 and out[0]["text"]
    # aviso automático: queda en la bandeja hasta que el puente la recoja
    with SessionLocal() as db:
        notify._deliver(db, db.get(M.Business, bid), "k-test", "noche", "Tu resumen de hoy", [])
    assert client.get("/webhook/bridge/outbox", headers=h).json()["outbox"][0]["text"] == "Tu resumen de hoy"


def test_30_explicaciones_con_sus_numeros_y_gastos_fijos(chat):
    """«¿Qué es…?» responde con los números del negocio; los gastos fijos se dicen por chat."""
    chat("vendí 2 polos en efectivo")
    r = chat("cuánto tengo que vender")["reply"]
    assert "gastos fijos" in r and "S/ 0" not in r   # sin gastos fijos: los pide, no dice «vende S/ 0»
    r = chat("pago 250 de alquiler del puesto al mes")["reply"]
    assert r.startswith("✓ Anoté tu gasto: Alquiler del puesto S/ 250 al mes (fijo)") and "al día" in r
    r = chat("bolsas 15 a la semana")["reply"]
    assert "Bolsas S/ 15 a la semana (variable)" in r
    assert "S/ 250 al mes" in chat("qué es el punto de equilibrio")["reply"]
    assert "semana" in chat("qué es la rotación")["reply"]   # con pocos días no inventa «238 días»
    assert "S/ 40" in chat("qué es la ganancia")["reply"] or "ganaste" in chat("qué es la ganancia")["reply"]


def test_31_corregir_el_producto_nombrado_y_compra_no_es_gasto(chat):
    """«corrige, el polo fue 30» corrige la última venta de ESE producto; comprar mercadería no baja la ganancia."""
    chat("vendí un polo en efectivo")
    chat("vendí una docena de polos")
    chat("efectivo")
    chat("gasté 5 en bolsas en efectivo")
    r = chat("corrige, el polo fue 30")["reply"]
    assert "S/ 30" in r
    d0 = chat("resumen")["reply"]
    chat("compré 12 polos a 144 en efectivo")
    d1 = chat("resumen")["reply"]
    gan = lambda t: t.split("Ganancia del día: ")[1].split(".")[0]
    assert gan(d0) == gan(d1) and "Compraste mercadería por S/ 144" in d1 and "Gastaste S/ 5 del negocio" in d1


def test_32_empezar_de_nuevo_por_whatsapp(client, monkeypatch):
    """«empezar de nuevo» pide confirmación; solo «sí, borrar todo» borra el negocio de ese número."""
    from app import main, whatsapp
    from app.config import settings
    from app.db import SessionLocal
    from app import models as M
    monkeypatch.setattr(settings, "whatsapp_enabled", True)
    sent = []
    monkeypatch.setattr(whatsapp, "send_text", lambda to, body, quick=None: sent.append(body))
    n = [0]

    def wa(t):
        n[0] += 1
        main._wa_process([{"id": f"r{n[0]}", "from": "51999000111", "type": "text", "text": t, "timestamp": None}])
        return sent[-1]
    assert "¿Cómo te llamas?" in wa("hola")
    wa("Juana")
    assert "Esto borra TODO" in wa("empezar de nuevo")
    wa("verduras: tomate y papa")                        # otra cosa: no borra, sigue la conversación
    from sqlalchemy import select
    with SessionLocal() as db:
        assert db.scalar(select(M.Business).where(M.Business.phone == "51999000111")).owner_name == "Juana"
    wa("empezar de nuevo")
    assert wa("sí, borrar todo").startswith("Listo, borré todo")
    assert "¿Cómo te llamas?" in wa("hola")


def test_33_fiado_con_fracciones(client, veg):
    """«medio kilo … fiado» es ½ kg (no 5 kg) y nunca deja a la persona sin respuesta."""
    from tests.conftest import Chat
    chat = Chat(client, veg)
    r = chat("la señora Carmen se llevó medio kilo de papa fiado")["reply"]
    assert "S/ 1.25" in r and "½" in r and "(Carmen)" in r
    r = chat("Ana se llevó kilo y medio de papa fiado")["reply"]
    assert "S/ 3.75" in r and "(Ana)" in r


def test_34_audio_sin_ia_explica_la_causa(client, monkeypatch):
    """Sin IA ni Whisper en el servidor, el audio no queda en «no pude escuchar»: dice qué falta."""
    from app import main, transcribe, whatsapp
    from app.config import settings
    monkeypatch.setattr(settings, "whatsapp_enabled", True)
    monkeypatch.setattr(settings, "agent_enabled", False)

    def no_whisper(*a, **k):
        raise transcribe.TranscriptionUnavailable("whisper no instalado")
    monkeypatch.setattr(transcribe, "transcribe_bytes", no_whisper)
    sent = []
    monkeypatch.setattr(whatsapp, "send_text", lambda to, body, quick=None: sent.append(body))
    main._wa_process([{"id": "au1", "from": "51999000222", "type": "audio", "audio_bytes": b"ogg", "timestamp": None}])
    assert "falta activar la IA" in sent[-1]


def test_35_metas_propuestas_al_terminar_la_bienvenida(client):
    """Al terminar la primera conversación propone metas con sus números, explica «por qué» y guarda la elegida."""
    b = client.post("/api/businesses", json={}).json()
    n = [0]

    def c(t):
        n[0] += 1
        return client.post(f"/api/businesses/{b['id']}/chat", json={"text": t, "message_id": f"g{n[0]}"}).json()
    for t in ["hola", "Juana", "verduras: tomate y papa", "eso es todo", "por kilo", "a 3, me cuesta 2", "a 2.50, me cuesta 1.80",
              "el tomate por jaba de 20 kilos a 40 soles y la papa por kilo", "1 jaba de tomate y 10 kilos de papa", "las dos",
              "alquiler del puesto 250 al mes y luz 40 al mes", "eso es todo", "100 en efectivo y 20 en yape"]:
        c(t)
    r = c("sí")
    assert "Ponerte una meta" in r["reply"] or "ponerte una meta" in r["reply"]
    assert "1️⃣ Reponer tu mercadería" in r["reply"] and "2️⃣ Tus gastos fijos del mes: S/ 290" in r["reply"]
    assert "Responde 1, 2 o 3" in r["reply"]
    assert "llenar tu puesto" in c("¿por qué la 1?")["reply"]
    assert "Separando" in c("¿por qué la 2?")["reply"]
    assert c("vendí una jaba de tomate en efectivo")["reply"].startswith("✓")   # una venta no elige meta
    assert "Aún no tienes una meta" in c("resumen")["reply"]
    assert "1️⃣" in c("metas")["reply"]
    r = c("la 2")["reply"]
    assert r.startswith("✓ ¡Meta guardada! «Mis gastos fijos del mes»: S/ 290")
    assert "Aún no tienes una meta" not in c("resumen")["reply"]


def test_36_gemini_transcribe_rapido_y_con_respaldo(client, monkeypatch):
    """Gemini solo transcribe, «pensando poco»; si el modelo no acepta esa opción prueba otra; si tarda, avisa."""
    import httpx
    from app import agent, main, whatsapp
    from app.config import settings
    monkeypatch.setattr(settings, "agent_enabled", True)
    monkeypatch.setattr(settings, "gemini_api_key", "k")
    agent._thinking_ok.clear()
    seen = []

    class R:
        def __init__(self, code, js=None):
            self.status_code, self._js, self.text = code, js, "bad thinking"
        def raise_for_status(self):
            if self.status_code >= 400:
                raise httpx.HTTPStatusError("x", request=None, response=None)
        def json(self):
            return self._js

    def post(url, json=None, headers=None, timeout=None):
        seen.append((json["generationConfig"].get("thinkingConfig"), timeout))
        if len(seen) == 1:
            return R(400)
        return R(200, {"candidates": [{"content": {"parts": [{"text": "pensando...", "thought": True}, {"text": "vendí 2 kilos de papa"}]}}]})
    monkeypatch.setattr(httpx, "post", post)
    assert agent.transcribe_audio(b"ogg") == "vendí 2 kilos de papa"
    assert seen[0][0] == {"thinkingLevel": "low"} and seen[1][0] == {"thinkingBudget": 0} and seen[1][1] <= 10
    agent.transcribe_audio(b"ogg")
    assert seen[-1][0] == {"thinkingBudget": 0}    # recuerda la opción que funcionó

    def slow(*a, **k):
        raise httpx.ReadTimeout("The read operation timed out")
    monkeypatch.setattr(httpx, "post", slow)
    monkeypatch.setattr(settings, "whatsapp_enabled", True)
    sent = []
    monkeypatch.setattr(whatsapp, "send_text", lambda to, body, quick=None: sent.append(body))
    main._wa_process([{"id": "slow1", "from": "51999000333", "type": "audio", "audio_bytes": b"ogg", "timestamp": None}])
    assert "La IA no pudo escuchar tu audio" in sent[-1]
    agent._thinking_ok.clear()


def test_37_informe_formal_pdf_y_por_whatsapp(client, monkeypatch):
    """Informe formal en PDF (solo Yape verificado), CSV con el detalle y envío del PDF por WhatsApp."""
    from app import report_pdf, twilio_wa
    from app.config import settings
    from app.db import SessionLocal
    from app.seed import seed_all
    from app import models as M
    with SessionLocal() as db:
        seed_all(db)
        bs = db.query(M.Business).all()
        for b in bs:
            a = report_pdf.analyze(db, b)
            assert a["code"].startswith("KAL-") and len(a["indicators"]) == 8 and a["profile"]
            assert a["available_installment_cents"] == max(0, (a["capacity"]["suggested_max_installment_cents"] or 0)
                                                           - (a["capacity"]["current_installments_cents"] or 0))
        bid, phone, n_mov = bs[0].id, bs[0].phone, len(report_pdf.build_bcp(db, bs[0])["movements"])
    r = client.get(f"/api/businesses/{bid}/report/pdf")
    assert r.status_code == 200 and r.content[:4] == b"%PDF" and r.headers["content-type"] == "application/pdf"
    csv = client.get(f"/api/businesses/{bid}/report/movimientos.csv").content.decode("utf-8-sig")
    assert csv.startswith("fecha,tipo,sentido") and len(csv.strip().split("\n")) == n_mov + 1
    for k, v in {"whatsapp_enabled": True, "whatsapp_provider": "twilio", "twilio_account_sid": "AC", "twilio_auth_token": "t",
                 "twilio_validate": False, "app_base_url": "https://kallpa.test"}.items():
        monkeypatch.setattr(settings, k, v)
    r = client.post("/webhook/twilio", data={"MessageSid": "SMinf", "From": f"whatsapp:+{phone}", "Body": "informe", "NumMedia": "0"})
    assert "Tu informe financiero" in r.text and f"<Media>https://kallpa.test/api/businesses/{bid}/report/pdf</Media>" in r.text
