"""Adaptador para correr el backend dentro del navegador (Pyodide), sin servidor.

Atiende las mismas rutas /api/... que app/main.py llamando a los mismos módulos
(conversación, caja, métricas, reporte). Se usa solo para la demo publicada en un link.
"""
from __future__ import annotations

import json
import re
import sys
import types
import uuid
from datetime import date, datetime

# Gemini no se usa en la demo del navegador: plantillas locales.
_g = types.ModuleType("app.gemini")


class GeminiUnavailable(RuntimeError):
    pass


def _propose(_d):
    raise GeminiUnavailable("IA externa desactivada en la demo")


_g.GeminiUnavailable = GeminiUnavailable
_g.propose = _propose
sys.modules["app.gemini"] = _g

from sqlalchemy import select  # noqa: E402

from app import conversation, ledger, metrics, notify, reconcile, report, setup, summaries  # noqa: E402
from app import models as M  # noqa: E402
from app.db import SessionLocal, init_db  # noqa: E402
from app.seed import delete_business, reset_demo, seed_all  # noqa: E402
from app.yape import yape_verify  # noqa: E402
from app.templates import TEMPLATES  # noqa: E402
from app.timeutil import LIMA, month_label, now_lima  # noqa: E402


class HTTPError(Exception):
    def __init__(self, status, detail):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def boot():
    init_db()
    with SessionLocal() as db:
        seed_all(db)
    return "ok"


def bview(b):
    return {"id": b.id, "name": b.name, "owner_name": b.owner_name, "kind": b.kind, "description": b.description,
            "setup_state": b.setup_state, "setup_source": b.setup_source, "setup_proposal": b.setup_proposal,
            "payment_methods": b.payment_methods, "demo": b.demo, "phone": b.phone,
            "gemini_requests": b.gemini_requests, "created_at": b.created_at.isoformat()}


def biz(db, bid):
    b = db.get(M.Business, int(bid))
    if not b:
        raise HTTPError(404, "Negocio no encontrado")
    return b


def occurred(v):
    if not v:
        return None
    d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    if d.tzinfo is not None:
        d = d.astimezone(LIMA).replace(tzinfo=None)
    return d.replace(microsecond=0)


def mv_detail(db, mid):
    mv = db.get(M.Movement, int(mid))
    if not mv:
        raise HTTPError(404, "No encontrado")
    v = conversation.movement_view(db, mv)
    v["revisions"] = [{"changed_at": r.changed_at.isoformat(), "before": r.before, "after": r.after, "reason": r.reason}
                      for r in db.scalars(select(M.MovementRevision).where(M.MovementRevision.movement_id == mv.id)
                                          .order_by(M.MovementRevision.id)).all()]
    v["yape"] = [{"payer": y.payer, "amount_cents": y.amount_cents, "operation_code": y.operation_code, "demo": y.demo}
                 for y in db.scalars(select(M.YapePayment).where(M.YapePayment.movement_id == mv.id)).all()]
    return v


def consent_status(db, b):
    eng = conversation.Engine(db, b, f"web:{b.id}")
    prev = eng.pending_consent_month()
    return {"pending_month": prev.strftime("%Y-%m") if prev else None, "pending_label": month_label(prev) if prev else None,
            "history": [{"month": c.month, "decision": c.decision, "decided_at": c.decided_at.isoformat()}
                        for c in db.scalars(select(M.ReportConsent).where(M.ReportConsent.business_id == b.id)
                                            .order_by(M.ReportConsent.month.desc())).all()]}


def list_fixed(db, bid):
    from app.costs import FREQ_LABEL, monthly_cents
    return [{"id": f.id, "name": f.name, "amount_cents": f.amount_cents, "due_day": f.due_day,
             "frequency": f.frequency or "mensual", "frequency_label": FREQ_LABEL.get(f.frequency or "mensual"),
             "cost_type": f.cost_type or "fijo", "monthly_cents": monthly_cents(f.amount_cents, f.frequency)}
            for f in db.scalars(select(M.FixedExpense).where(M.FixedExpense.business_id == int(bid))).all()]


def list_debts(db, bid):
    out = []
    for d in db.scalars(select(M.Debt).where(M.Debt.business_id == int(bid))).all():
        paid = sum(m.amount_cents for m in metrics.movements(db, int(bid), kinds={M.DEBT_PAYMENT}) if m.debt_id == d.id)
        out.append({"id": d.id, "creditor": d.creditor, "total_cents": d.total_cents, "installment_cents": d.installment_cents,
                    "due_day": d.due_day, "active": d.active, "paid_cents": paid, "remaining_cents": max(0, d.total_cents - paid)})
    return out


def list_assets(db, bid):
    return [{"id": a.id, "name": a.name, "value_cents": a.value_cents}
            for a in db.scalars(select(M.Asset).where(M.Asset.business_id == int(bid))).all()]


NO_VOICE = "La voz del servidor no está en esta vista previa: uso el dictado del navegador o escribe."
ROUTES = []


def route(method, pattern):
    def deco(fn):
        ROUTES.append((method, re.compile("^" + pattern + "$"), fn))
        return fn
    return deco


@route("GET", r"/api/health")
def r_health(db, q, body):
    return {"ok": True, "time_lima": now_lima().isoformat(),
            "transcription": {"installed": False, "model_on_disk": False, "loaded": False, "model": "base", "error": NO_VOICE},
            "gemini": {"enabled": False, "model": "plantillas locales"},
            "whatsapp": {"connected": False, "number": "", "status": "pendiente de conectar"},
            "templates": {k: v["label"] for k, v in TEMPLATES.items()}, "browser_demo": True}


@route("GET", r"/api/businesses")
def r_list(db, q, body):
    return [bview(b) for b in db.scalars(select(M.Business).order_by(M.Business.demo.desc(), M.Business.id)).all()]


@route("POST", r"/api/businesses")
def r_create(db, q, body):
    b = M.Business(name=body.get("name") or "Mi negocio", owner_name=body.get("owner_name"), setup_state="pendiente")
    db.add(b)
    db.commit()
    return bview(b)


@route("GET", r"/api/businesses/(\d+)")
def r_get(db, q, body, bid):
    return bview(biz(db, bid))


@route("PATCH", r"/api/businesses/(\d+)")
def r_patch(db, q, body, bid):
    b = biz(db, bid)
    b.name = body.get("name") or b.name
    b.owner_name = body.get("owner_name")
    if body.get("phone") is not None:
        digits = "".join(ch for ch in body["phone"] if ch.isdigit())
        b.phone = (("51" + digits) if len(digits) == 9 else digits) or None
    db.commit()
    return bview(b)


@route("DELETE", r"/api/businesses/(\d+)")
def r_del(db, q, body, bid):
    delete_business(db, biz(db, bid))
    db.commit()
    return {"ok": True}


@route("POST", r"/api/businesses/(\d+)/setup/propose")
def r_propose(db, q, body, bid):
    b = biz(db, bid)
    p = setup.propose(db, b, body["description"], use_ai=False)
    return {"proposal": p, "text": setup.proposal_text(p)}


@route("POST", r"/api/businesses/(\d+)/setup/confirm")
def r_confirm(db, q, body, bid):
    b = biz(db, bid)
    p = body.get("proposal")
    if p:
        p.setdefault("source", (b.setup_proposal or {}).get("source", "manual"))
    setup.apply(db, b, p)
    return bview(b)


@route("POST", r"/api/businesses/(\d+)/setup/template")
def r_template(db, q, body, bid):
    b = biz(db, bid)
    setup.from_template(db, b, body["kind"])
    return bview(b)


@route("POST", r"/api/businesses/(\d+)/(?:setup/transcribe-propose|chat/audio)")
def r_noaudio(db, q, body, bid):
    raise HTTPError(503, NO_VOICE)


@route("POST", r"/api/businesses/(\d+)/chat")
def r_chat(db, q, body, bid):
    b = biz(db, bid)
    ch = "whatsapp" if body.get("channel") == "whatsapp" else "web"
    conv = f"whatsapp:{b.phone or 'app-' + str(b.id)}" if ch == "whatsapp" else None
    return conversation.process_message(db, b, body.get("text", ""), message_id=body.get("message_id") or uuid.uuid4().hex,
                                        channel=ch, conversation=conv, op_id=body.get("op_id"), occurred_at=occurred(body.get("recorded_at")),
                                        via_voice=bool(body.get("via_voice")))


@route("GET", r"/api/businesses/(\d+)/chat/history")
def r_hist(db, q, body, bid):
    limit = int(q.get("limit", 60))
    qq = select(M.ChatLog).where(M.ChatLog.business_id == int(bid))
    if q.get("channel"):
        qq = qq.where(M.ChatLog.channel.in_((q["channel"], "aviso")))
    rows = db.scalars(qq.order_by(M.ChatLog.id.desc()).limit(limit)).all()
    return [{"id": r.id, "role": r.role, "text": r.text, "channel": r.channel, "via_voice": r.via_voice,
             "created_at": r.created_at.isoformat()} for r in reversed(rows)]


@route("GET", r"/api/businesses/(\d+)/chat/pending")
def r_pending(db, q, body, bid):
    b = biz(db, bid)
    conv = f"whatsapp:{b.phone or 'app-' + str(b.id)}" if q.get("channel") == "whatsapp" else f"web:{bid}"
    d = db.scalar(select(M.Draft).where(M.Draft.business_id == int(bid), M.Draft.conversation == conv,
                                        M.Draft.status == "abierto").order_by(M.Draft.id.desc()))
    return {"draft": {"op_id": d.op_id, "action": d.action, "missing": d.missing, "data": d.data} if d else None}


@route("GET", r"/api/businesses/(\d+)/dashboard")
def r_dash(db, q, body, bid):
    b = biz(db, bid)
    data = metrics.dashboard(db, b)
    data["daily_text"] = summaries.daily(db, b)
    data["consent"] = consent_status(db, b)
    return notify.enrich(db, b, data)


@route("GET", r"/api/businesses/(\d+)/notifications")
def r_notes(db, q, body, bid):
    return notify.latest(db, biz(db, bid), 20)


@route("POST", r"/api/businesses/(\d+)/notifications/run")
def r_run(db, q, body, bid):
    created = notify.run(db, biz(db, bid), force=q.get("slot"))
    return [{"kind": n.kind, "text": n.text, "sent_whatsapp": n.sent_whatsapp} for n in created]


@route("GET", r"/api/businesses/(\d+)/receivables")
def r_recv(db, q, body, bid):
    return notify.overdue_receivables(db, biz(db, bid), 0)


@route("GET", r"/api/businesses/(\d+)/summary")
def r_summary(db, q, body, bid):
    b = biz(db, bid)
    fn = {"dia": summaries.daily, "semana": summaries.weekly, "mes": summaries.monthly}[q.get("period", "dia")]
    return {"text": fn(db, b)}


@route("GET", r"/api/businesses/(\d+)/movements")
def r_movs(db, q, body, bid):
    s = select(M.Movement).where(M.Movement.business_id == int(bid))
    if q.get("kind"):
        s = s.where(M.Movement.kind == q["kind"])
    if q.get("include_void") == "false":
        s = s.where(M.Movement.status == "confirmado")
    rows = db.scalars(s.order_by(M.Movement.occurred_at.desc(), M.Movement.id.desc()).limit(int(q.get("limit", 80)))).all()
    return [conversation.movement_view(db, m) for m in rows]


@route("POST", r"/api/businesses/(\d+)/movements")
def r_newmov(db, q, body, bid):
    b = biz(db, bid)
    data = {k: v for k, v in body.items() if k != "op_id"}
    data["occurred_at"] = occurred(body.get("occurred_at")) or now_lima()
    try:
        mv, created = ledger.record(db, b, data, op_id=body["op_id"], channel="app")
    except ledger.LedgerError as e:
        db.rollback()
        raise HTTPError(422, str(e))
    v = conversation.movement_view(db, mv)
    v["created"] = created
    return v


@route("GET", r"/api/movements/(\d+)")
def r_mov(db, q, body, mid):
    return mv_detail(db, mid)


ALLOWED = {"amount_cents", "paid_cents", "method", "to_method", "product_id", "quantity", "category", "counterparty",
           "description", "expense_type", "occurred_at"}


@route("PATCH", r"/api/movements/(\d+)")
def r_revise(db, q, body, mid):
    mv = db.get(M.Movement, int(mid))
    if not mv or mv.status != "confirmado":
        raise HTTPError(404, "Movimiento no encontrado o anulado")
    changes = {k: v for k, v in (body.get("changes") or {}).items() if k in ALLOWED}
    try:
        ledger.revise(db, db.get(M.Business, mv.business_id), mv, changes, reason=body.get("reason") or "corrección desde la app")
    except ledger.LedgerError as e:
        db.rollback()
        raise HTTPError(422, str(e))
    return mv_detail(db, mid)


@route("POST", r"/api/movements/(\d+)/void")
def r_void(db, q, body, mid):
    mv = db.get(M.Movement, int(mid))
    if mv and mv.status == "confirmado":
        ledger.void(db, mv, reason="anulado desde la app")
    return mv_detail(db, mid)


@route("POST", r"/api/movements/(\d+)/attachments")
def r_attach(db, q, body, mid):
    raise HTTPError(503, "Los adjuntos se guardan en el servidor; no están en esta vista previa.")


@route("GET", r"/api/businesses/(\d+)/inventory")
def r_inv(db, q, body, bid):
    return metrics.inventory(db, biz(db, bid))


@route("POST", r"/api/businesses/(\d+)/products")
def r_newprod(db, q, body, bid):
    biz(db, bid)
    keys = {"name", "aliases", "price_cents", "cost_cents", "initial_stock", "reorder_point", "track_stock", "is_service", "is_input", "unit"}
    p = M.Product(business_id=int(bid), **{k: v for k, v in body.items() if k in keys})
    db.add(p)
    db.commit()
    return {"id": p.id}


@route("PATCH", r"/api/products/(\d+)")
def r_prod(db, q, body, pid):
    p = db.get(M.Product, int(pid))
    if not p:
        raise HTTPError(404, "No encontrado")
    for k in ("name", "aliases", "price_cents", "cost_cents", "reorder_point", "track_stock", "active", "unit"):
        if k in body:
            setattr(p, k, body[k])
    if body.get("current_stock") is not None:
        p.initial_stock = int(body["current_stock"]) - ledger.stock_delta(db, p.id)
    elif "initial_stock" in body:
        p.initial_stock = body["initial_stock"]
    db.commit()
    return {"ok": True}


@route("POST", r"/api/businesses/(\d+)/counts")
def r_count(db, q, body, bid):
    b = biz(db, bid)
    if body["kind"] == "stock":
        p = db.get(M.Product, int(body.get("product_id") or 0))
        if not p or p.business_id != b.id:
            raise HTTPError(404, "Producto no encontrado")
        c = reconcile.stock_count(db, b, p, int(body["counted"]))
    else:
        c = reconcile.cash_count(db, b, body.get("pocket") or "efectivo", int(body["counted"]))
    d = metrics._count_dict(c)
    d["text"] = reconcile.count_text(db, c)
    return d


@route("POST", r"/api/counts/(\d+)/resolve")
def r_resolve(db, q, body, cid):
    c = db.get(M.Count, int(cid))
    if not c:
        raise HTTPError(404, "No encontrado")
    reconcile.resolve_count(db, db.get(M.Business, c.business_id), c, body["action"], body.get("note"))
    return metrics._count_dict(c)


@route("GET", r"/api/businesses/(\d+)/reconciliation")
def r_rec(db, q, body, bid):
    return reconcile.summary(db, biz(db, bid))


@route("GET", r"/api/businesses/(\d+)/goals")
def r_goals(db, q, body, bid):
    return metrics.goals(db, biz(db, bid))


@route("POST", r"/api/businesses/(\d+)/goals")
def r_newgoal(db, q, body, bid):
    b = biz(db, bid)
    g = M.Goal(business_id=b.id, kind=body["kind"], name=body["name"], target_cents=int(body["target_cents"]),
               deadline=date.fromisoformat(body["deadline"]) if body.get("deadline") else None,
               product_id=body.get("product_id"), quantity=body.get("quantity"))
    db.add(g)
    db.commit()
    return metrics.goal_status(db, b, g)


@route("PATCH", r"/api/goals/(\d+)")
def r_goal(db, q, body, gid):
    g = db.get(M.Goal, int(gid))
    if not g:
        raise HTTPError(404, "No encontrado")
    for k in ("name", "target_cents", "status"):
        if k in body:
            setattr(g, k, body[k])
    if "deadline" in body:
        g.deadline = date.fromisoformat(body["deadline"]) if body["deadline"] else None
    db.commit()
    return metrics.goal_status(db, db.get(M.Business, g.business_id), g)


@route("GET", r"/api/businesses/(\d+)/fixed-expenses")
def r_fixed(db, q, body, bid):
    return list_fixed(db, bid)


@route("POST", r"/api/businesses/(\d+)/fixed-expenses")
def r_addfixed(db, q, body, bid):
    biz(db, bid)
    from app.costs import classify
    freq = body.get("frequency") or "mensual"
    db.add(M.FixedExpense(business_id=int(bid), name=body["name"], amount_cents=int(body["amount_cents"]),
                          due_day=int(body.get("due_day") or 1), frequency=freq,
                          cost_type=body.get("cost_type") or classify(body["name"], freq)))
    db.commit()
    return list_fixed(db, bid)


@route("DELETE", r"/api/fixed-expenses/(\d+)")
def r_delfixed(db, q, body, fid):
    f = db.get(M.FixedExpense, int(fid))
    if f:
        db.delete(f)
        db.commit()
    return {"ok": True}


@route("GET", r"/api/businesses/(\d+)/debts")
def r_debts(db, q, body, bid):
    return list_debts(db, bid)


@route("POST", r"/api/businesses/(\d+)/debts")
def r_adddebt(db, q, body, bid):
    biz(db, bid)
    db.add(M.Debt(business_id=int(bid), creditor=body["creditor"], total_cents=int(body["total_cents"]),
                  installment_cents=int(body["installment_cents"]), due_day=int(body["due_day"]),
                  installments_total=body.get("installments_total")))
    db.commit()
    return list_debts(db, bid)


@route("GET", r"/api/businesses/(\d+)/assets")
def r_assets(db, q, body, bid):
    return list_assets(db, bid)


@route("POST", r"/api/businesses/(\d+)/assets")
def r_addasset(db, q, body, bid):
    biz(db, bid)
    db.add(M.Asset(business_id=int(bid), name=body["name"], value_cents=int(body["value_cents"])))
    db.commit()
    return list_assets(db, bid)


@route("POST", r"/api/businesses/(\d+)/opening")
def r_opening(db, q, body, bid):
    b = biz(db, bid)
    eng = conversation.Engine(db, b, f"app:{b.id}", "app")
    bal = {k: body.get(f"{k}_cents") for k in ("efectivo", "yape") if body.get(f"{k}_cents") is not None}
    if not bal:
        raise HTTPError(422, "Indica al menos un saldo")
    d = eng.new_draft("saldo", {"balances": bal})
    eng.confirm_balance(d)
    return metrics.cash_position(db, b)


@route("GET", r"/api/businesses/(\d+)/report")
def r_report(db, q, body, bid):
    s = date.fromisoformat(q["start"]) if q.get("start") else None
    e = date.fromisoformat(q["end"]) if q.get("end") else None
    return report.build_bcp(db, biz(db, bid), s, e)


@route("POST", r"/api/businesses/(\d+)/yape/demo")
def r_yape(db, q, body, bid):
    return yape_verify(db, biz(db, bid), body)


@route("GET", r"/api/businesses/(\d+)/report/consent")
def r_consent(db, q, body, bid):
    return consent_status(db, biz(db, bid))


@route("POST", r"/api/businesses/(\d+)/report/consent")
def r_setconsent(db, q, body, bid):
    b = biz(db, bid)
    c = db.scalar(select(M.ReportConsent).where(M.ReportConsent.business_id == b.id, M.ReportConsent.month == body["month"]))
    if c:
        c.decision = body["decision"]
        c.decided_at = now_lima()
    else:
        db.add(M.ReportConsent(business_id=b.id, month=body["month"], decision=body["decision"]))
    for d in db.scalars(select(M.Draft).where(M.Draft.business_id == b.id, M.Draft.action == "consentimiento",
                                              M.Draft.status == "abierto")).all():
        d.status = "confirmado"
    db.commit()
    return consent_status(db, b)


@route("POST", r"/api/demo/reset")
def r_reset(db, q, body):
    reset_demo(db)
    return r_list(db, q, body)


@route("POST", r"/api/businesses/(\d+)/whatsapp/daily-summary")
def r_wa(db, q, body, bid):
    b = biz(db, bid)
    return {"sent": False, "text": summaries.daily(db, b), "reason": "WhatsApp pendiente de conectar"}


def handle(method, path, query_json, body_json):
    """Devuelve JSON {"status": int, "body": ...}."""
    q = json.loads(query_json or "{}")
    body = json.loads(body_json) if body_json else {}
    for m, rx, fn in ROUTES:
        if m != method:
            continue
        mt = rx.match(path)
        if mt:
            with SessionLocal() as db:
                try:
                    res = fn(db, q, body, *mt.groups())
                    return json.dumps({"status": 200, "body": res}, default=str)
                except HTTPError as e:
                    db.rollback()
                    return json.dumps({"status": e.status, "body": {"detail": e.detail}})
                except ledger.LedgerError as e:
                    db.rollback()
                    return json.dumps({"status": 422, "body": {"detail": str(e)}})
    return json.dumps({"status": 404, "body": {"detail": "Ruta no encontrada"}})
