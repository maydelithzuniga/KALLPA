import os
import sys
import tempfile
from pathlib import Path

_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = os.getenv("TEST_DATABASE_URL") or f"sqlite:///{_tmp}/test.db"
os.environ["SEED_DEMO"] = "false"
os.environ["GEMINI_ENABLED"] = "false"
os.environ["WHATSAPP_ENABLED"] = "false"
os.environ["NOTIFY_AUTO"] = "false"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture()
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def shop(client):
    """Negocio de reventa con «Polo» a S/20, costo S/12, stock 10 y caja inicial conocida."""
    b = client.post("/api/businesses", json={"name": "Tienda test", "owner_name": "Ana"}).json()
    client.post(f"/api/businesses/{b['id']}/setup/template", json={"kind": "reventa"})
    inv = client.get(f"/api/businesses/{b['id']}/inventory").json()
    pid = inv[0]["id"]
    client.patch(f"/api/products/{pid}", json={"name": "Polo", "price_cents": 2000, "cost_cents": 1200, "initial_stock": 10})
    client.post(f"/api/businesses/{b['id']}/opening", json={"efectivo_cents": 10000, "yape_cents": 5000})
    return {"id": b["id"], "pid": pid}


class Chat:
    def __init__(self, client, bid):
        self.c = client
        self.bid = bid
        self.n = 0

    def __call__(self, text, message_id=None, **kw):
        self.n += 1
        body = {"text": text, "message_id": message_id or f"m{self.n}-{text[:10]}", **kw}
        r = self.c.post(f"/api/businesses/{self.bid}/chat", json=body)
        assert r.status_code == 200, r.text
        return r.json()


@pytest.fixture()
def chat(client, shop):
    return Chat(client, shop["id"])
