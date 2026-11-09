"""Casos de aceptación del MVP (sección «Entrega y criterios de aceptación»)."""
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


def test_1b_configuracion_por_chat(client):
    b = client.post("/api/businesses", json={"name": "Mi negocio"}).json()
    c = lambda t, i: client.post(f"/api/businesses/{b['id']}/chat", json={"text": t, "message_id": i}).json()
    assert "Cuéntame qué vendes" in c("hola", "a")["reply"]
    r = c("Vendo polos, compro por docena y cobro por Yape y en efectivo", "b")
    assert "reventa" in r["reply"]
    r = c("sí", "c")
    assert "configurado" in r["reply"]


# 2 ---------------------------------------------------------------------------
def test_2_venta_con_descuento_e_idempotencia(client, shop, chat):
    bid, pid = shop["id"], shop["pid"]
    before = dash(client, bid)["cash"]
    r = chat("Vendí tres polos por cincuenta soles en efectivo", message_id="audio-1")
    assert r["reply"] == "Tres polos, S/ 50 en efectivo, con S/ 10 de descuento. ¿Lo guardo?"
    # nada cambia antes de confirmar
    assert dash(client, bid)["cash"]["efectivo_cents"] == before["efectivo_cents"]
    op = r["draft"]["op_id"]
    r2 = chat("sí", message_id="audio-2")
    assert r2["movement"]["discount_cents"] == 1000
    assert r2["movement"]["amount_cents"] == 5000
    assert r2["movement"]["unit_price_ref_cents"] == 2000
    after = dash(client, bid)["cash"]
    assert after["efectivo_cents"] == before["efectivo_cents"] + 5000
    assert stock(client, bid, pid) == 7
    # reenviar el mismo evento y repetir la confirmación no duplica
    assert chat("Vendí tres polos por cincuenta soles en efectivo", message_id="audio-1")["duplicate"] is True
    assert chat("sí", message_id="audio-2")["duplicate"] is True
    assert chat("sí", message_id="otro", op_id=op)["duplicate"] is True
    assert "nada pendiente" in chat("sí", message_id="otro-2")["reply"]
    assert dash(client, bid)["cash"]["efectivo_cents"] == before["efectivo_cents"] + 5000
    assert stock(client, bid, pid) == 7
    sales = client.get(f"/api/businesses/{bid}/movements?kind=venta").json()
    assert len(sales) == 1


def test_2b_audio_real_pasa_por_transcripcion_una_sola_vez(client, shop, monkeypatch):
    bid = shop["id"]
    calls = []

    def fake(data, suffix):
        calls.append(data)
        return "Vendí tres polos por cincuenta soles en efectivo" if len(calls) == 1 else "sí"

    monkeypatch.setattr(transcribe, "transcribe_bytes", fake)
    post = lambda mid: client.post(f"/api/businesses/{bid}/chat/audio",
                                   files={"audio": ("a.webm", io.BytesIO(b"fake-audio"), "audio/webm")},
                                   data={"message_id": mid}).json()
    r = post("rec-1")
    assert r["transcript"].startswith("Vendí tres polos")
    assert "S/ 10 de descuento" in r["reply"]
    assert post("rec-1")["duplicate"] is True        # reintento del mismo audio
    assert len(calls) == 1                            # no se volvió a transcribir
    r = post("rec-2")                                 # «sí» por voz
    assert r["movement"]["amount_cents"] == 5000


def test_2c_ambiguedades_y_medio_de_pago_que_confirma(client, shop, chat):
    bid = shop["id"]
    r = chat("vendí tres polos a S/60")
    assert "total o el precio de cada uno" in r["reply"]
    r = chat("es el total")
    assert "¿En efectivo o por Yape?" in r["reply"] and r["draft"]["missing"] == "method"
    r = chat("en efectivo")                     # completa y confirma el mismo borrador
    assert r["movement"]["amount_cents"] == 6000 and r["movement"]["discount_cents"] == 0
    r = chat("vendí 2 polos a 25 cada uno por yape")
    assert "S/ 50 por Yape" in r["reply"]
    r = chat("sí")
    assert r["movement"]["discount_cents"] == 0       # precio superior al habitual
    r = chat("vendí 2 polos por 40 por yape y por 30")
    assert "dos montos" in r["reply"] or "total" in r["reply"]


def test_2d_fiado_parcial_y_cobro_vinculado(client, shop, chat):
    bid = shop["id"]
    base = dash(client, bid)["cash"]["efectivo_cents"]
    r = chat("vendí 2 polos por 40 a la señora Juana, me pagó 30 y me debe 10 en efectivo")
    assert "te debe S/ 10" in r["reply"]
    sale = chat("sí")["movement"]
    assert sale["paid_cents"] == 3000 and sale["pending_cents"] == 1000
    assert dash(client, bid)["cash"]["efectivo_cents"] == base + 3000
    r = chat("Juana me pagó 10 del fiado en efectivo")
    r = chat("sí")
    assert r["movement"]["parent_id"] == sale["id"]
    assert "Ya no te debe nada" in r["reply"]
    assert dash(client, bid)["receivables"] == []


def test_2e_correccion_conserva_historial(client, shop, chat):
    bid, pid = shop["id"], shop["pid"]
    chat("Vendí tres polos por cincuenta soles en efectivo")
    mv = chat("sí")["movement"]
    r = chat("corrige: eran dos polos")
    assert "Corrijo" in r["reply"]
    chat("sí")
    m = client.get(f"/api/movements/{mv['id']}").json()
    assert m["quantity"] == 2 and m["revision"] == 2 and len(m["revisions"]) == 1
    assert m["discount_cents"] == 0  # 2 x 20 = 40 < 50
    assert stock(client, bid, pid) == 8


# 3 ---------------------------------------------------------------------------
def test_3_compra_por_docena(client, shop, chat):
    bid, pid = shop["id"], shop["pid"]
    yape0 = dash(client, bid)["cash"]["yape_cents"]
    r = chat("Compré una docena de polos por S/144 en total y pagué por Yape")
    assert "S/ 12 cada uno" in r["reply"]
    mv = chat("sí")["movement"]
    assert mv["quantity"] == 12 and mv["amount_cents"] == 14400 and mv["unit_cost_cents"] == 1200
    assert stock(client, bid, pid) == 22
    assert dash(client, bid)["cash"]["yape_cents"] == yape0 - 14400
    # compra sin unidades
    r = chat("compré mercadería por 144 en efectivo")
    mv = chat("sí")["movement"]
    assert mv["units_pending"] is True and mv["quantity"] is None


# 4 ---------------------------------------------------------------------------
def test_4_conciliacion_de_stock_y_reporte(client, shop, chat):
    bid, pid = shop["id"], shop["pid"]
    chat("Compré una docena de polos por S/144 en total y pagué por Yape")
    chat("sí")                                     # 10 + 12 = 22
    chat("Vendí tres polos por cincuenta soles en efectivo")
    chat("sí")                                     # 22 - 3 = 19
    assert stock(client, bid, pid) == 19
    r = chat("conté 17 polos")
    assert "faltan 2" in r["reply"]
    assert r["count"]["expected"] == 19 and r["count"]["difference"] == -2 and r["count"]["result"] == "diferencia"
    rec = client.get(f"/api/businesses/{bid}/reconciliation").json()
    assert rec["open"] and rec["open"][0]["hints"]
    client.post(f"/api/counts/{r['count']['id']}/resolve", json={"action": "pendiente"})
    rep = client.get(f"/api/businesses/{bid}/report").json()
    sale = next(m for m in rep["movements"] if m["kind"] == "venta")
    assert sale["amount_cents"] == 5000 and sale["discount_cents"] == 1000 and sale["reference_total_cents"] == 6000
    assert sale["origin"] == "Autodeclarado" and sale["check"] == "Con diferencia"
    assert rep["reconciliation"]["open"][0]["difference"] == -2
    assert rep["summary"]["discounts_cents"] == 1000


def test_4b_respaldo_yape_y_conteo_de_caja(client, shop, chat):
    bid = shop["id"]
    chat("vendí un polo en 20 por yape")
    mv = chat("sí")["movement"]
    assert mv["origin"] == "autodeclarado"
    link = client.post(f"/api/businesses/{bid}/yape/demo", json={"payer": "Lucía", "amount_cents": 2000}).json()
    assert link["linked_movement_id"] == mv["id"]
    assert client.get(f"/api/movements/{mv['id']}").json()["origin"] == "respaldo_yape"
    r = chat("tengo 90 en efectivo en caja")
    assert r["count"]["expected"] == 10000 and r["count"]["difference"] == -1000


# 5 ---------------------------------------------------------------------------
def test_5_aportes_y_traslados_no_inflan_ventas(client, shop, chat):
    bid = shop["id"]
    d0 = dash(client, bid)
    chat("puse 200 de mi bolsillo al negocio en efectivo")
    assert chat("sí")["movement"]["kind"] == "aporte"
    chat("pasé 100 de yape a efectivo")
    assert chat("sí")["movement"]["kind"] == "traslado"
    chat("me saqué 50 para la casa en efectivo")
    assert chat("sí")["movement"]["kind"] == "retiro_personal"
    d1 = dash(client, bid)
    assert d1["day"]["sales_cents"] == 0
    assert d1["day"]["contributions_cents"] == 20000
    assert d1["day"]["withdrawals_cents"] == 5000
    assert d1["day"]["expenses_cents"] == 0                     # el retiro no es gasto del negocio
    assert d1["cash"]["efectivo_cents"] == d0["cash"]["efectivo_cents"] + 20000 + 10000 - 5000
    assert d1["cash"]["yape_cents"] == d0["cash"]["yape_cents"] - 10000
    assert d1["cash"]["total_cents"] == d0["cash"]["total_cents"] + 15000


def test_5b_audio_pendiente_solo_cambia_caja_tras_confirmar(client, shop, monkeypatch):
    bid = shop["id"]
    seq = iter(["gasté 40 en pasajes en efectivo", "sí"])
    monkeypatch.setattr(transcribe, "transcribe_bytes", lambda d, s: next(seq))
    e0 = dash(client, bid)["cash"]["efectivo_cents"]
    send = lambda mid: client.post(f"/api/businesses/{bid}/chat/audio",
                                   files={"audio": ("p.webm", io.BytesIO(b"x"), "audio/webm")},
                                   data={"message_id": mid, "recorded_at": "2026-11-06T10:00:00-05:00"}).json()
    r = send("offline-1")
    assert "¿Lo guardo?" in r["reply"]
    send("offline-1")
    send("offline-1")
    assert dash(client, bid)["cash"]["efectivo_cents"] == e0      # aún sin confirmar
    r = send("offline-2")
    assert r["movement"]["amount_cents"] == 4000
    assert r["movement"]["occurred_at"].startswith("2026-11-06T10:00")
    send("offline-2")
    assert dash(client, bid)["cash"]["efectivo_cents"] == e0 - 4000


# 6 ---------------------------------------------------------------------------
def test_6_meta_de_reposicion_y_reporte_coincide(client, shop, chat):
    bid = shop["id"]
    client.post(f"/api/businesses/{bid}/fixed-expenses", json={"name": "Luz", "amount_cents": 5000, "due_day": 28})
    g = client.post(f"/api/businesses/{bid}/goals", json={"kind": "reposicion", "name": "Reponer polos", "target_cents": 20000}).json()
    assert "Tu próxima compra cuesta S/ 200" in g["message"]
    chat("Vendí tres polos por cincuenta soles en efectivo")
    chat("sí")
    chat("pagué la luz 30 en efectivo")
    chat("sí")
    d = dash(client, bid)
    goal = next(x for x in d["goals"] if x["kind"] == "reposicion")
    cash = d["cash"]
    assert goal["available_cents"] == cash["total_cents"] - cash["upcoming_total_cents"]
    assert "Te faltan" in goal["message"] or "alcanza" in goal["message"]
    rep = client.get(f"/api/businesses/{bid}/report").json()
    movs = client.get(f"/api/businesses/{bid}/movements?include_void=false").json()
    sales = sum(m["amount_cents"] for m in movs if m["kind"] == "venta")
    exp = sum(m["amount_cents"] for m in movs if m["kind"] == "gasto")
    assert rep["summary"]["sales_cents"] == sales == 5000
    assert rep["summary"]["expenses_cents"] == exp == 3000
    assert rep["summary"]["collected_by_method"]["efectivo"] == 5000


def test_catalogo_cuesta_ambiguo(client, shop, chat):
    r = chat("Mi polo cuesta S/20 y tengo diez en stock")
    assert "precio al que lo vendes o lo que te cuesta" in r["reply"]
    r = chat("me cuesta eso")
    assert "costo de compra S/ 20" in r["reply"]
    r = chat("sí")
    assert "Listo" in r["reply"]


def test_meta_de_ahorro_por_chat(client, shop, chat):
    r = chat("quiero juntar 1500 para una congeladora en 10 semanas")
    assert "Congeladora" in r["reply"] and "por semana" in r["reply"]
    chat("sí")
    chat("separé 30 para la congeladora en efectivo")
    r = chat("sí")
    assert "2%" in r["reply"]


def test_explicacion_flujo_de_caja(client, shop, chat):
    chat("Vendí tres polos por cincuenta soles en efectivo"); chat("sí")
    r = chat("¿Qué es eso del flujo de caja?")
    assert r["reply"].startswith("Es la plata que de verdad tienes en la mano para usar")
