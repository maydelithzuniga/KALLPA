"""API FastAPI: chat web y WhatsApp unificados, panel, inventario, metas, conciliación y reporte."""
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import conversation, inbox, ledger, metrics, notify, reconcile, report, setup, summaries, transcribe, whatsapp
from . import models as M
from .config import BASE_DIR, settings
from .db import SessionLocal, get_db, init_db
from .money import soles
from .seed import delete_business, reset_demo, seed_all
from .yape import yape_verify
from .templates import TEMPLATES
from .timeutil import add_months, month_label, month_start, now_lima, today_lima

log = logging.getLogger("kallpa")
logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpx2").setLevel(logging.WARNING)
UPLOADS = BASE_DIR / "uploads"
UPLOADS.mkdir(exist_ok=True)

from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(_app):
    init_db()
    if settings.seed_demo:
        with SessionLocal() as db:
            seed_all(db)
    yield


app = FastAPI(title="Kallpa — asistente financiero", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_origin_regex=r"https?://(localhost|127\.0\.0\.1|192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+)(:\d+)?",
                   allow_methods=["*"], allow_headers=["*"])


def biz(db: Session, business_id: int) -> M.Business:
    b = db.get(M.Business, business_id)
    if not b:
        raise HTTPException(404, "Negocio no encontrado")
    return b


def business_view(b: M.Business) -> dict[str, Any]:
    return {"id": b.id, "name": b.name, "owner_name": b.owner_name, "kind": b.kind, "description": b.description,
            "setup_state": b.setup_state, "setup_source": b.setup_source, "setup_proposal": b.setup_proposal,
            "payment_methods": b.payment_methods, "demo": b.demo, "phone": b.phone,
            "gemini_requests": b.gemini_requests, "created_at": b.created_at.isoformat()}


# ------------------------------------------------------------------ estado

@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok": True, "time_lima": now_lima().isoformat(), "transcription": transcribe.status(),
            "gemini": {"enabled": settings.gemini_available, "model": settings.gemini_model},
            "agent": {"enabled": settings.agent_enabled and bool(settings.gemini_api_key), "model": settings.agent_model,
                      "voice_reply": settings.agent_voice_reply},
            "whatsapp": {"connected": settings.whatsapp_available, "provider": settings.whatsapp_provider,
                         "number": __import__("os").getenv("WHATSAPP_DISPLAY_NUMBER", "") or
                         ("".join(ch for ch in settings.twilio_whatsapp_from if ch.isdigit()) if settings.whatsapp_provider == "twilio" else ""),
                         "join_code": settings.twilio_join_code if settings.whatsapp_provider == "twilio" else "",
                         "status": "conectado" if settings.whatsapp_available else "pendiente de conectar"},
            "templates": {k: v["label"] for k, v in TEMPLATES.items()}}


# ------------------------------------------------------------------ negocios

class BusinessIn(BaseModel):
    name: str = Field(default="Mi negocio", max_length=120)
    owner_name: str | None = Field(default=None, max_length=80)
    phone: str | None = Field(default=None, max_length=30)   # WhatsApp de la emprendedora (con código de país)


@app.get("/api/businesses")
def list_businesses(db: Session = Depends(get_db)):
    return [business_view(b) for b in db.scalars(select(M.Business).order_by(M.Business.demo.desc(), M.Business.id)).all()]


@app.post("/api/businesses")
def create_business(body: BusinessIn, db: Session = Depends(get_db)):
    b = M.Business(name=body.name or "Mi negocio", owner_name=body.owner_name, setup_state="pendiente")
    db.add(b)
    db.commit()
    return business_view(b)


@app.get("/api/businesses/{business_id}")
def get_business(business_id: int, db: Session = Depends(get_db)):
    return business_view(biz(db, business_id))


@app.patch("/api/businesses/{business_id}")
def update_business(business_id: int, body: BusinessIn, db: Session = Depends(get_db)):
    b = biz(db, business_id)
    b.name = body.name
    b.owner_name = body.owner_name
    if body.phone is not None:
        digits = "".join(ch for ch in body.phone if ch.isdigit())
        if digits and len(digits) == 9:
            digits = "51" + digits          # celular peruano sin código de país
        if digits:
            other = db.scalar(select(M.Business).where(M.Business.phone == digits, M.Business.id != b.id))
            if other is not None:
                raise HTTPException(409, "Ese número ya está vinculado a otro negocio")
        b.phone = digits or None
    db.commit()
    return business_view(b)


@app.delete("/api/businesses/{business_id}")
def remove_business(business_id: int, db: Session = Depends(get_db)):
    b = biz(db, business_id)
    delete_business(db, b)
    db.commit()
    return {"ok": True}


class ProposeIn(BaseModel):
    description: str = Field(min_length=3, max_length=600)
    use_ai: bool = True


@app.post("/api/businesses/{business_id}/setup/propose")
def setup_propose(business_id: int, body: ProposeIn, db: Session = Depends(get_db)):
    b = biz(db, business_id)
    p = setup.propose(db, b, body.description, use_ai=body.use_ai)
    return {"proposal": p, "text": setup.proposal_text(p)}


@app.post("/api/businesses/{business_id}/setup/transcribe-propose")
async def setup_voice(business_id: int, audio: UploadFile = File(...), use_ai: bool = Form(True), db: Session = Depends(get_db)):
    b = biz(db, business_id)
    text = await _transcribe(audio)
    p = setup.propose(db, b, text, use_ai=use_ai)
    return {"transcript": text, "proposal": p, "text": setup.proposal_text(p)}


class ConfirmSetupIn(BaseModel):
    proposal: dict[str, Any] | None = None


@app.post("/api/businesses/{business_id}/setup/confirm")
def setup_confirm(business_id: int, body: ConfirmSetupIn, db: Session = Depends(get_db)):
    b = biz(db, business_id)
    if body.proposal:
        body.proposal.setdefault("source", (b.setup_proposal or {}).get("source", "manual"))
    setup.apply(db, b, body.proposal)
    return business_view(b)


class TemplateIn(BaseModel):
    kind: Literal["reventa", "verduras", "comida", "servicios"]


@app.post("/api/businesses/{business_id}/setup/template")
def setup_template(business_id: int, body: TemplateIn, db: Session = Depends(get_db)):
    b = biz(db, business_id)
    setup.from_template(db, b, body.kind)
    return business_view(b)


# ------------------------------------------------------------------ chat

class ChatIn(BaseModel):
    text: str = Field(max_length=1000)
    message_id: str | None = Field(default=None, max_length=128)
    op_id: str | None = Field(default=None, max_length=64)
    recorded_at: datetime | None = None
    via_voice: bool = False
    channel: Literal["web", "whatsapp"] = "web"   # «whatsapp»: vista de WhatsApp dentro de la app (mismo agente y datos)


def _occurred(recorded_at: datetime | None) -> datetime | None:
    if recorded_at is None:
        return None
    if recorded_at.tzinfo is not None:
        from .timeutil import LIMA
        recorded_at = recorded_at.astimezone(LIMA).replace(tzinfo=None)
    return recorded_at.replace(microsecond=0)


@app.post("/api/businesses/{business_id}/chat")
def chat(business_id: int, body: ChatIn, db: Session = Depends(get_db)):
    b = biz(db, business_id)
    conv = f"whatsapp:{b.phone or 'app-' + str(b.id)}" if body.channel == "whatsapp" else None
    return inbox.receive(db, b, text=body.text, message_id=body.message_id or uuid.uuid4().hex, channel=body.channel,
                         conversation=conv, op_id=body.op_id, occurred_at=_occurred(body.recorded_at))


async def _transcribe(audio: UploadFile) -> str:
    data = await audio.read()
    if not data:
        raise HTTPException(400, "Audio vacío")
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(413, "Audio demasiado grande")
    suffix = Path(audio.filename or "audio.webm").suffix or ".webm"
    try:
        import anyio
        return await anyio.to_thread.run_sync(transcribe.transcribe_bytes, data, suffix)
    except transcribe.TranscriptionUnavailable as e:
        raise HTTPException(503, f"Transcripción no disponible: {e}")


@app.post("/api/businesses/{business_id}/chat/audio")
async def chat_audio(business_id: int, audio: UploadFile = File(...), message_id: str = Form(...),
                     recorded_at: str | None = Form(None), op_id: str | None = Form(None),
                     channel: Literal["web", "whatsapp"] = Form("web"), db: Session = Depends(get_db)):
    b = biz(db, business_id)
    prev = db.scalar(select(M.ProcessedMessage).where(M.ProcessedMessage.message_id == message_id))
    if prev:   # reintento de un audio pendiente: no se procesa otra vez
        r = dict(prev.response)
        r["duplicate"] = True
        return r
    data = await audio.read()
    if not data:
        raise HTTPException(400, "Audio vacío")
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(413, "Audio demasiado grande")
    suffix = Path(audio.filename or "audio.webm").suffix or ".webm"
    mime = (audio.content_type or "audio/webm").split(";")[0]
    rec = _occurred(datetime.fromisoformat(recorded_at.replace("Z", "+00:00"))) if recorded_at else None
    import anyio
    try:
        conv = f"whatsapp:{b.phone or 'app-' + str(b.id)}" if channel == "whatsapp" else None
        return await anyio.to_thread.run_sync(lambda: inbox.receive(db, b, audio=data, mime_type=mime, suffix=suffix, message_id=message_id,
                                                                   channel=channel, conversation=conv, op_id=op_id, occurred_at=rec))
    except transcribe.TranscriptionUnavailable as e:
        raise HTTPException(503, f"Transcripción no disponible: {e}")
    except inbox.NotUnderstood:
        return {"reply": "No escuché bien el audio. ¿Me lo repites?", "transcript": "", "quick_replies": [], "draft": None,
                "message_id": message_id}


@app.get("/api/businesses/{business_id}/chat/history")
def chat_history(business_id: int, limit: int = 60, channel: str | None = None, db: Session = Depends(get_db)):
    q = select(M.ChatLog).where(M.ChatLog.business_id == business_id)
    if channel:   # cada canal ve su conversación (los mensajes automáticos aparecen en ambos)
        q = q.where(M.ChatLog.channel.in_((channel, "aviso")))
    rows = db.scalars(q.order_by(M.ChatLog.id.desc()).limit(limit)).all()
    return [{"id": r.id, "role": r.role, "text": r.text, "channel": r.channel, "via_voice": r.via_voice,
             "created_at": r.created_at.isoformat()} for r in reversed(rows)]


@app.get("/api/businesses/{business_id}/chat/pending")
def chat_pending(business_id: int, channel: str = "web", db: Session = Depends(get_db)):
    b = biz(db, business_id)
    conv = f"whatsapp:{b.phone or 'app-' + str(b.id)}" if channel == "whatsapp" else f"web:{business_id}"
    d = db.scalar(select(M.Draft).where(M.Draft.business_id == business_id, M.Draft.conversation == conv,
                                        M.Draft.status == "abierto").order_by(M.Draft.id.desc()))
    return {"draft": {"op_id": d.op_id, "action": d.action, "missing": d.missing, "data": d.data} if d else None}


# ------------------------------------------------------------------ panel y resúmenes

@app.get("/api/businesses/{business_id}/dashboard")
def dashboard(business_id: int, db: Session = Depends(get_db)):
    b = biz(db, business_id)
    data = metrics.dashboard(db, b)
    data["daily_text"] = summaries.daily(db, b)
    data["consent"] = consent_status(business_id, db)
    return notify.enrich(db, b, data)


@app.get("/api/businesses/{business_id}/summary")
def summary(business_id: int, period: Literal["dia", "semana", "mes"] = "dia", db: Session = Depends(get_db)):
    b = biz(db, business_id)
    fn = {"dia": summaries.daily, "semana": summaries.weekly, "mes": summaries.monthly}[period]
    return {"text": fn(db, b)}


# ------------------------------------------------------------------ movimientos

@app.get("/api/businesses/{business_id}/movements")
def list_movements(business_id: int, limit: int = Query(80, le=500), kind: str | None = None,
                   include_void: bool = True, db: Session = Depends(get_db)):
    q = select(M.Movement).where(M.Movement.business_id == business_id)
    if kind:
        q = q.where(M.Movement.kind == kind)
    if not include_void:
        q = q.where(M.Movement.status == "confirmado")
    rows = db.scalars(q.order_by(M.Movement.occurred_at.desc(), M.Movement.id.desc()).limit(limit)).all()
    return [conversation.movement_view(db, m) for m in rows]


@app.get("/api/movements/{movement_id}")
def get_movement(movement_id: int, db: Session = Depends(get_db)):
    mv = db.get(M.Movement, movement_id)
    if not mv:
        raise HTTPException(404)
    v = conversation.movement_view(db, mv)
    v["revisions"] = [{"changed_at": r.changed_at.isoformat(), "before": r.before, "after": r.after, "reason": r.reason}
                      for r in db.scalars(select(M.MovementRevision).where(M.MovementRevision.movement_id == mv.id)
                                          .order_by(M.MovementRevision.id)).all()]
    v["yape"] = [{"payer": y.payer, "amount_cents": y.amount_cents, "operation_code": y.operation_code, "demo": y.demo}
                 for y in db.scalars(select(M.YapePayment).where(M.YapePayment.movement_id == mv.id)).all()]
    return v


class MovementIn(BaseModel):
    kind: str
    amount_cents: int = Field(ge=0)
    method: str | None = None
    to_method: str | None = None
    product_id: int | None = None
    quantity: int | None = None
    paid_cents: int | None = None
    category: str | None = None
    expense_type: str | None = None
    counterparty: str | None = None
    description: str | None = None
    parent_id: int | None = None
    goal_id: int | None = None
    debt_id: int | None = None
    reason: str | None = None
    occurred_at: datetime | None = None
    op_id: str = Field(min_length=6, max_length=64)


@app.post("/api/businesses/{business_id}/movements")
def create_movement(business_id: int, body: MovementIn, db: Session = Depends(get_db)):
    """Registro manual desde la app (formulario). Idempotente por op_id."""
    b = biz(db, business_id)
    data = body.model_dump(exclude={"op_id"})
    data["occurred_at"] = _occurred(body.occurred_at) or now_lima()
    try:
        mv, created = ledger.record(db, b, data, op_id=body.op_id, channel="app")
    except ledger.LedgerError as e:
        raise HTTPException(422, str(e))
    v = conversation.movement_view(db, mv)
    v["created"] = created
    return v


class ReviseIn(BaseModel):
    changes: dict[str, Any]
    reason: str | None = None


ALLOWED_CHANGES = {"amount_cents", "paid_cents", "method", "to_method", "product_id", "quantity", "category", "counterparty",
                   "description", "expense_type", "occurred_at"}


@app.patch("/api/movements/{movement_id}")
def revise_movement(movement_id: int, body: ReviseIn, db: Session = Depends(get_db)):
    mv = db.get(M.Movement, movement_id)
    if not mv or mv.status != "confirmado":
        raise HTTPException(404, "Movimiento no encontrado o anulado")
    changes = {k: v for k, v in body.changes.items() if k in ALLOWED_CHANGES}
    try:
        ledger.revise(db, db.get(M.Business, mv.business_id), mv, changes, reason=body.reason or "corrección desde la app")
    except ledger.LedgerError as e:
        db.rollback()
        raise HTTPException(422, str(e))
    return get_movement(movement_id, db)


@app.post("/api/movements/{movement_id}/void")
def void_movement(movement_id: int, db: Session = Depends(get_db)):
    mv = db.get(M.Movement, movement_id)
    if not mv:
        raise HTTPException(404)
    if mv.status == "confirmado":
        ledger.void(db, mv, reason="anulado desde la app")
    return get_movement(movement_id, db)


@app.post("/api/movements/{movement_id}/attachments")
async def add_attachment(movement_id: int, file: UploadFile = File(...),
                         kind: Literal["comprobante_proveedor", "captura_yape", "otro"] = Form("otro"),
                         db: Session = Depends(get_db)):
    mv = db.get(M.Movement, movement_id)
    if not mv:
        raise HTTPException(404)
    data = await file.read()
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(413, "Archivo demasiado grande")
    safe = f"{movement_id}-{uuid.uuid4().hex[:8]}{Path(file.filename or 'adjunto').suffix[:6]}"
    (UPLOADS / safe).write_bytes(data)
    db.add(M.Attachment(movement_id=mv.id, kind=kind, filename=safe))
    if mv.origin == "autodeclarado":
        # un comprobante de proveedor respalda una compra; cualquier otro adjunto queda como «con adjunto»
        mv.origin = "comprobante" if (kind == "comprobante_proveedor" and mv.kind == M.PURCHASE) else "con_adjunto"
    db.commit()
    return get_movement(movement_id, db)


@app.get("/audio/{filename}")
def voice_reply_file(filename: str):
    """Audios de respuesta (Edge-TTS) que WhatsApp descarga para enviarlos a la emprendedora."""
    path = (whatsapp.VOICE_DIR / filename).resolve()
    if path.parent != whatsapp.VOICE_DIR.resolve() or not path.exists():
        raise HTTPException(404)
    return FileResponse(path, media_type="audio/mpeg")


@app.get("/api/attachments/{filename}")
def get_attachment(filename: str):
    path = (UPLOADS / filename).resolve()
    if path.parent != UPLOADS.resolve() or not path.exists():
        raise HTTPException(404)
    return FileResponse(path)


# ------------------------------------------------------------------ productos e inventario

class ProductIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    aliases: list[str] = []
    price_cents: int | None = Field(default=None, ge=0)
    cost_cents: int | None = Field(default=None, ge=0)
    initial_stock: int | None = None
    reorder_point: int | None = None
    track_stock: bool = True
    is_service: bool = False
    is_input: bool = False
    unit: str = "unidad"


@app.get("/api/businesses/{business_id}/inventory")
def get_inventory(business_id: int, db: Session = Depends(get_db)):
    return metrics.inventory(db, biz(db, business_id))


@app.post("/api/businesses/{business_id}/products")
def create_product(business_id: int, body: ProductIn, db: Session = Depends(get_db)):
    biz(db, business_id)
    p = M.Product(business_id=business_id, **body.model_dump())
    db.add(p)
    db.commit()
    return {"id": p.id}


@app.patch("/api/products/{product_id}")
def update_product(product_id: int, body: dict[str, Any], db: Session = Depends(get_db)):
    p = db.get(M.Product, product_id)
    if not p:
        raise HTTPException(404)
    for k in ("name", "aliases", "price_cents", "cost_cents", "reorder_point", "track_stock", "active", "unit"):
        if k in body:
            setattr(p, k, body[k])
    if "current_stock" in body and body["current_stock"] is not None:
        # declarar stock actual cuando no había stock inicial
        p.initial_stock = int(body["current_stock"]) - ledger.stock_delta(db, p.id)
    elif "initial_stock" in body:
        p.initial_stock = body["initial_stock"]
    db.commit()
    return {"ok": True}


class CountIn(BaseModel):
    kind: Literal["stock", "caja"]
    product_id: int | None = None
    pocket: Literal["efectivo", "yape"] | None = None
    counted: int


@app.post("/api/businesses/{business_id}/counts")
def create_count(business_id: int, body: CountIn, db: Session = Depends(get_db)):
    b = biz(db, business_id)
    if body.kind == "stock":
        p = db.get(M.Product, body.product_id or 0)
        if not p or p.business_id != b.id:
            raise HTTPException(404, "Producto no encontrado")
        c = reconcile.stock_count(db, b, p, body.counted)
    else:
        c = reconcile.cash_count(db, b, body.pocket or "efectivo", body.counted)
    d = metrics._count_dict(c)
    d["text"] = reconcile.count_text(db, c)
    return d


class ResolveIn(BaseModel):
    action: Literal["ajustar", "pendiente", "revisado"]
    note: str | None = None


@app.post("/api/counts/{count_id}/resolve")
def resolve_count(count_id: int, body: ResolveIn, db: Session = Depends(get_db)):
    c = db.get(M.Count, count_id)
    if not c:
        raise HTTPException(404)
    reconcile.resolve_count(db, db.get(M.Business, c.business_id), c, body.action, body.note)
    return metrics._count_dict(c)


@app.get("/api/businesses/{business_id}/reconciliation")
def reconciliation(business_id: int, db: Session = Depends(get_db)):
    return reconcile.summary(db, biz(db, business_id))


# ------------------------------------------------------------------ metas, gastos fijos, deudas, equipos, saldos

class GoalIn(BaseModel):
    kind: Literal["reposicion", "ahorro"]
    name: str = Field(min_length=1, max_length=80)
    target_cents: int = Field(gt=0)
    deadline: date | None = None
    product_id: int | None = None
    quantity: int | None = None


@app.get("/api/businesses/{business_id}/goals")
def list_goals(business_id: int, db: Session = Depends(get_db)):
    return metrics.goals(db, biz(db, business_id))


@app.post("/api/businesses/{business_id}/goals")
def create_goal(business_id: int, body: GoalIn, db: Session = Depends(get_db)):
    b = biz(db, business_id)
    g = M.Goal(business_id=b.id, **body.model_dump())
    db.add(g)
    db.commit()
    return metrics.goal_status(db, b, g)


@app.patch("/api/goals/{goal_id}")
def update_goal(goal_id: int, body: dict[str, Any], db: Session = Depends(get_db)):
    g = db.get(M.Goal, goal_id)
    if not g:
        raise HTTPException(404)
    for k in ("name", "target_cents", "status"):
        if k in body:
            setattr(g, k, body[k])
    if "deadline" in body:
        g.deadline = date.fromisoformat(body["deadline"]) if body["deadline"] else None
    db.commit()
    return metrics.goal_status(db, db.get(M.Business, g.business_id), g)


class FixedIn(BaseModel):
    name: str
    amount_cents: int = Field(gt=0)
    due_day: int = Field(ge=1, le=31)


@app.get("/api/businesses/{business_id}/fixed-expenses")
def list_fixed(business_id: int, db: Session = Depends(get_db)):
    return [{"id": f.id, "name": f.name, "amount_cents": f.amount_cents, "due_day": f.due_day}
            for f in db.scalars(select(M.FixedExpense).where(M.FixedExpense.business_id == business_id)).all()]


@app.post("/api/businesses/{business_id}/fixed-expenses")
def add_fixed(business_id: int, body: FixedIn, db: Session = Depends(get_db)):
    biz(db, business_id)
    db.add(M.FixedExpense(business_id=business_id, **body.model_dump()))
    db.commit()
    return list_fixed(business_id, db)


@app.delete("/api/fixed-expenses/{fid}")
def del_fixed(fid: int, db: Session = Depends(get_db)):
    f = db.get(M.FixedExpense, fid)
    if f:
        db.delete(f)
        db.commit()
    return {"ok": True}


class DebtIn(BaseModel):
    creditor: str
    total_cents: int = Field(gt=0)
    installment_cents: int = Field(gt=0)
    due_day: int = Field(ge=1, le=31)
    installments_total: int | None = None


@app.get("/api/businesses/{business_id}/debts")
def list_debts(business_id: int, db: Session = Depends(get_db)):
    out = []
    for d in db.scalars(select(M.Debt).where(M.Debt.business_id == business_id)).all():
        paid = sum(m.amount_cents for m in metrics.movements(db, business_id, kinds={M.DEBT_PAYMENT}) if m.debt_id == d.id)
        out.append({"id": d.id, "creditor": d.creditor, "total_cents": d.total_cents, "installment_cents": d.installment_cents,
                    "due_day": d.due_day, "active": d.active, "paid_cents": paid, "remaining_cents": max(0, d.total_cents - paid)})
    return out


@app.post("/api/businesses/{business_id}/debts")
def add_debt(business_id: int, body: DebtIn, db: Session = Depends(get_db)):
    biz(db, business_id)
    db.add(M.Debt(business_id=business_id, **body.model_dump()))
    db.commit()
    return list_debts(business_id, db)


class AssetIn(BaseModel):
    name: str
    value_cents: int = Field(gt=0)


@app.get("/api/businesses/{business_id}/assets")
def list_assets(business_id: int, db: Session = Depends(get_db)):
    return [{"id": a.id, "name": a.name, "value_cents": a.value_cents}
            for a in db.scalars(select(M.Asset).where(M.Asset.business_id == business_id)).all()]


@app.post("/api/businesses/{business_id}/assets")
def add_asset(business_id: int, body: AssetIn, db: Session = Depends(get_db)):
    biz(db, business_id)
    db.add(M.Asset(business_id=business_id, **body.model_dump()))
    db.commit()
    return list_assets(business_id, db)


class OpeningIn(BaseModel):
    efectivo_cents: int | None = Field(default=None, ge=0)
    yape_cents: int | None = Field(default=None, ge=0)


@app.post("/api/businesses/{business_id}/opening")
def set_opening(business_id: int, body: OpeningIn, db: Session = Depends(get_db)):
    b = biz(db, business_id)
    eng = conversation.Engine(db, b, f"app:{b.id}", "app")
    bal = {k: v for k, v in (("efectivo", body.efectivo_cents), ("yape", body.yape_cents)) if v is not None}
    if not bal:
        raise HTTPException(422, "Indica al menos un saldo")
    d = eng.new_draft("saldo", {"balances": bal})
    eng.confirm_balance(d)
    return metrics.cash_position(db, b)


# ------------------------------------------------------------------ reporte y consentimiento

@app.get("/api/businesses/{business_id}/report")
def get_report(business_id: int, start: date | None = None, end: date | None = None, db: Session = Depends(get_db)):
    """Informe para BCP: solo ingresos y egresos por Yape verificados."""
    return report.build_bcp(db, biz(db, business_id), start, end)


@app.get("/api/businesses/{business_id}/report/full")
def get_report_full(business_id: int, start: date | None = None, end: date | None = None, db: Session = Depends(get_db)):
    """Reporte interno completo (efectivo y Yape, conciliación, descuentos). No se envía al banco."""
    return report.build(db, biz(db, business_id), start, end)


@app.get("/api/businesses/{business_id}/report/consent")
def consent_status(business_id: int, db: Session = Depends(get_db)):
    b = biz(db, business_id)
    eng = conversation.Engine(db, b, f"web:{b.id}")
    prev = eng.pending_consent_month()
    return {"pending_month": prev.strftime("%Y-%m") if prev else None, "pending_label": month_label(prev) if prev else None,
            "history": [{"month": c.month, "decision": c.decision, "decided_at": c.decided_at.isoformat()}
                        for c in db.scalars(select(M.ReportConsent).where(M.ReportConsent.business_id == b.id)
                                            .order_by(M.ReportConsent.month.desc())).all()]}


class ConsentIn(BaseModel):
    month: str = Field(pattern=r"^\d{4}-\d{2}$")
    decision: Literal["si", "no"]


@app.post("/api/businesses/{business_id}/report/consent")
def set_consent(business_id: int, body: ConsentIn, db: Session = Depends(get_db)):
    b = biz(db, business_id)
    c = db.scalar(select(M.ReportConsent).where(M.ReportConsent.business_id == b.id, M.ReportConsent.month == body.month))
    if c:
        c.decision = body.decision
        c.decided_at = now_lima()
    else:
        db.add(M.ReportConsent(business_id=b.id, month=body.month, decision=body.decision))
    for d in db.scalars(select(M.Draft).where(M.Draft.business_id == b.id, M.Draft.action == "consentimiento",
                                              M.Draft.status == "abierto")).all():
        d.status = "confirmado"
    db.commit()
    return consent_status(business_id, db)


# ------------------------------------------------------------------ resúmenes y alertas automáticos

@app.get("/api/businesses/{business_id}/notifications")
def list_notifications(business_id: int, db: Session = Depends(get_db)):
    return notify.latest(db, biz(db, business_id), 20)


@app.post("/api/businesses/{business_id}/notifications/run")
def run_notifications(business_id: int, slot: Literal["manana", "noche", "semana", "mes"] | None = None, db: Session = Depends(get_db)):
    """Genera los mensajes que tocan ahora (o fuerza uno para probar: manana, noche, semana, mes)."""
    created = notify.run(db, biz(db, business_id), force=slot)
    return [{"kind": n.kind, "text": n.text, "sent_whatsapp": n.sent_whatsapp} for n in created]


@app.post("/api/notifications/run-all")
def run_all_notifications(db: Session = Depends(get_db)):
    """Para un cron cada hora: revisa todos los negocios y envía lo que toque (máx. 2 mensajes al día)."""
    out = 0
    for b in db.scalars(select(M.Business).where(M.Business.setup_state == "listo")).all():
        out += len(notify.run(db, b))
    return {"sent": out}


@app.get("/api/businesses/{business_id}/receivables")
def receivables(business_id: int, db: Session = Depends(get_db)):
    return notify.overdue_receivables(db, biz(db, business_id), 0)


# ------------------------------------------------------------------ demo

@app.post("/api/demo/reset")
def demo_reset(db: Session = Depends(get_db)):
    reset_demo(db)
    return list_businesses(db)


class YapeIn(BaseModel):
    direction: Literal["entrada", "salida"] = "entrada"
    movement_id: int | None = None
    payer: str
    amount_cents: int = Field(gt=0)
    operation_code: str | None = None
    received_at: datetime | None = None


@app.post("/api/businesses/{business_id}/yape/demo")
def yape_demo(business_id: int, body: YapeIn, db: Session = Depends(get_db)):
    """Simula el registro de Yape (cobro o pago) y verifica el movimiento que coincide. Datos de demostración."""
    return yape_verify(db, biz(db, business_id), body.model_dump())


# ------------------------------------------------------------------ WhatsApp Cloud API

@app.get("/webhook/whatsapp")
def wa_verify(request: Request):
    q = request.query_params
    if q.get("hub.mode") == "subscribe" and settings.whatsapp_verify_token and q.get("hub.verify_token") == settings.whatsapp_verify_token:
        return PlainTextResponse(q.get("hub.challenge", ""))
    raise HTTPException(403, "Token de verificación inválido")


def _wa_business(db: Session, phone: str) -> M.Business:
    b = db.scalar(select(M.Business).where(M.Business.phone == phone))
    if not b:
        b = M.Business(name="Mi negocio", phone=phone, setup_state="pendiente")
        db.add(b)
        db.commit()
    return b


def _wa_process(msgs: list[dict[str, Any]]) -> None:
    with SessionLocal() as db:
        for m in msgs:
            if not m.get("id") or not m.get("from"):
                continue
            b = _wa_business(db, m["from"])
            mid = {"twilio": "tw", "bridge": "br"}.get(m.get("provider", ""), "wa") + f":{m['id']}"
            if db.scalar(select(M.ProcessedMessage).where(M.ProcessedMessage.message_id == mid)):
                continue   # Meta reintenta webhooks: no duplicar
            occurred = datetime.fromtimestamp(int(m["timestamp"]), tz=__import__("zoneinfo").ZoneInfo("America/Lima")).replace(tzinfo=None) \
                if m.get("timestamp") else None
            text = m.get("text")
            audio = None
            if m.get("audio_bytes") is not None:
                audio = m["audio_bytes"]
            elif m["type"] in ("audio", "voice") and (m.get("media_id") or m.get("media_url")):
                try:
                    if m.get("media_url"):
                        from . import twilio_wa
                        audio = twilio_wa.download_media(m["media_url"])
                    else:
                        audio = whatsapp.download_media(m["media_id"])
                except Exception as e:  # noqa: BLE001
                    log.warning("No se pudo descargar el audio de WhatsApp: %s", e)
            if not text and audio is None:
                continue
            try:
                r = inbox.receive(db, b, text=text, audio=audio, mime_type=(m.get("mime") or "audio/ogg").split(";")[0], suffix=".ogg", message_id=mid,
                                  channel="whatsapp", conversation=f"whatsapp:{m['from']}", occurred_at=occurred)
            except (transcribe.TranscriptionUnavailable, inbox.NotUnderstood) as e:
                log.warning("Audio de WhatsApp no entendido: %s", e)
                whatsapp.send_text(m["from"], "No pude escuchar bien tu audio. ¿Me lo repites o me lo escribes?")
                continue
            if r.get("duplicate"):
                continue
            heard = r.get("transcript")
            reply = (f"🎙️ «{heard}»\n" if heard else "") + r["reply"]
            whatsapp.send_text(m["from"], reply, r.get("quick_replies") or None)
            if audio is not None:
                whatsapp.send_voice_reply(m["from"], r["reply"], mid)


@app.post("/webhook/whatsapp")
async def wa_receive(request: Request, background: BackgroundTasks):
    raw = await request.body()
    if not whatsapp.verify_signature(raw, request.headers.get("X-Hub-Signature-256")):
        raise HTTPException(401, "Firma inválida")
    payload = await request.json()
    msgs = whatsapp.extract_messages(payload)
    if msgs and settings.whatsapp_available:
        background.add_task(_wa_process, msgs)
    return {"ok": True}


@app.post("/webhook/twilio")
async def twilio_receive(request: Request, background: BackgroundTasks):
    """WhatsApp por Twilio (Sandbox). Configúralo en Twilio: «When a message comes in» = https://TU-URL/webhook/twilio (POST)."""
    from . import twilio_wa
    form = {k: str(v) for k, v in (await request.form()).items()}
    url = str(request.url)
    candidates = [url, url.replace("http://", "https://", 1)]
    if settings.app_base_url:
        q = ("?" + request.url.query) if request.url.query else ""
        candidates.insert(0, settings.app_base_url.rstrip("/") + request.url.path + q)
    if not twilio_wa.verify_signature(candidates, form, request.headers.get("X-Twilio-Signature")):
        raise HTTPException(401, "Firma de Twilio inválida")
    m = twilio_wa.extract_message(form)
    if m and settings.whatsapp_available:
        m["provider"] = "twilio"
        background.add_task(_wa_process, [m])
    return Response(content="<Response></Response>", media_type="application/xml")


class BridgeIn(BaseModel):
    id: str
    from_: str = Field(alias="from")
    text: str | None = None
    audio_b64: str | None = None
    mime: str | None = None
    timestamp: int | None = None


def _bridge_auth(request: Request) -> None:
    import hmac as _h
    if settings.whatsapp_provider != "bridge" or not settings.bridge_secret or \
            not _h.compare_digest(request.headers.get("X-Bridge-Secret", ""), settings.bridge_secret):
        raise HTTPException(401, "Clave del puente inválida")


@app.post("/webhook/bridge")
def bridge_receive(body: BridgeIn, request: Request):
    """Puente gratis (carpeta bridge/): recibe el mensaje, lo procesa y devuelve lo que hay que contestar."""
    _bridge_auth(request)
    import base64 as _b64
    audio = _b64.b64decode(body.audio_b64) if body.audio_b64 else None
    m = {"id": body.id, "from": "".join(ch for ch in body.from_ if ch.isdigit()), "provider": "bridge",
         "type": "audio" if audio is not None else "text", "text": body.text, "audio_bytes": audio,
         "mime": body.mime, "timestamp": body.timestamp}
    if settings.whatsapp_available:
        _wa_process([m])
    return {"outbox": whatsapp.bridge_drain()}


@app.get("/webhook/bridge/outbox")
def bridge_outbox(request: Request):
    _bridge_auth(request)
    return {"outbox": whatsapp.bridge_drain()}


@app.post("/api/businesses/{business_id}/whatsapp/daily-summary")
def wa_daily(business_id: int, db: Session = Depends(get_db)):
    b = biz(db, business_id)
    text = summaries.daily(db, b)
    if settings.whatsapp_available and b.phone:
        whatsapp.send_text(b.phone, text)
        return {"sent": True, "text": text}
    return {"sent": False, "text": text, "reason": "WhatsApp pendiente de conectar"}


# ------------------------------------------------------------------ frontend estático (opcional)

DIST = BASE_DIR.parent / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        if full_path.startswith(("api/", "webhook/")):
            raise HTTPException(404)
        target = (DIST / full_path).resolve()
        if full_path and target.is_file() and DIST.resolve() in target.parents:
            return FileResponse(target)
        return FileResponse(DIST / "index.html")


@app.exception_handler(ledger.LedgerError)
def _ledger_error(_req, exc):
    return JSONResponse(status_code=422, content={"detail": str(exc)})


__all__ = ["app", "soles", "add_months", "month_start", "today_lima"]
