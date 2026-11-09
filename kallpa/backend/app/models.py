"""Modelo de datos. Todos los importes se guardan en céntimos enteros."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base
from .timeutil import now_lima

# Tipos de movimiento
SALE = "venta"
PURCHASE = "compra"
EXPENSE = "gasto"                 # gasto del negocio (fijo o variable)
WITHDRAWAL = "retiro_personal"     # plata sacada del negocio para la casa
CONTRIBUTION = "aporte"            # plata propia que entra al negocio
TRANSFER = "traslado"              # efectivo <-> yape
COLLECTION = "cobro_fiado"         # cobro posterior de una venta
DEBT_PAYMENT = "pago_deuda"        # cuota de una deuda
OPENING = "saldo_inicial"
STOCK_ADJ = "ajuste_stock"         # merma, devolución, ajuste
GOAL_SAVING = "ahorro_meta"        # separar plata para una meta

POCKETS = ("efectivo", "yape")


class Business(Base):
    __tablename__ = "businesses"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    owner_name: Mapped[str | None] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(20), default="reventa")  # reventa | comida | servicios
    description: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(String(30), unique=True)
    payment_methods: Mapped[list] = mapped_column(JSON, default=lambda: ["efectivo", "yape"])
    setup_state: Mapped[str] = mapped_column(String(20), default="pendiente")  # pendiente | propuesta | listo
    setup_source: Mapped[str | None] = mapped_column(String(20))  # gemini | plantilla | manual
    setup_proposal: Mapped[dict | None] = mapped_column(JSON)
    gemini_requests: Mapped[int] = mapped_column(Integer, default=0)
    demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_lima)

    products: Mapped[list[Product]] = relationship(back_populates="business", cascade="all, delete-orphan")


class Category(Base):
    __tablename__ = "categories"
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(60))
    kind: Mapped[str] = mapped_column(String(20))  # venta | compra | gasto_fijo | gasto_variable | personal


class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    aliases: Mapped[list] = mapped_column(JSON, default=list)
    unit: Mapped[str] = mapped_column(String(20), default="unidad")
    is_service: Mapped[bool] = mapped_column(Boolean, default=False)
    is_input: Mapped[bool] = mapped_column(Boolean, default=False)   # insumo (no se vende)
    track_stock: Mapped[bool] = mapped_column(Boolean, default=True)
    price_cents: Mapped[int | None] = mapped_column(Integer)          # precio habitual de venta
    cost_cents: Mapped[int | None] = mapped_column(Integer)           # último costo unitario de compra
    initial_stock: Mapped[int | None] = mapped_column(Integer)        # None = desconocido
    reorder_point: Mapped[int | None] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_lima)

    business: Mapped[Business] = relationship(back_populates="products")


class Movement(Base):
    __tablename__ = "movements"
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    op_id: Mapped[str] = mapped_column(String(64), unique=True)       # idempotencia de confirmación
    source_message_id: Mapped[str | None] = mapped_column(String(128))
    kind: Mapped[str] = mapped_column(String(20), index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=now_lima, index=True)
    amount_cents: Mapped[int] = mapped_column(Integer, default=0)     # venta: precio final acordado
    paid_cents: Mapped[int] = mapped_column(Integer, default=0)       # lo cobrado/pagado en el momento
    method: Mapped[str | None] = mapped_column(String(12))            # efectivo | yape
    to_method: Mapped[str | None] = mapped_column(String(12))         # traslado: destino
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"))
    quantity: Mapped[int | None] = mapped_column(Integer)
    unit_price_ref_cents: Mapped[int | None] = mapped_column(Integer)  # precio habitual aplicado
    reference_total_cents: Mapped[int | None] = mapped_column(Integer)
    discount_cents: Mapped[int | None] = mapped_column(Integer)        # None = sin calcular
    unit_cost_cents: Mapped[int | None] = mapped_column(Integer)       # compra: costo unitario; venta: costo vigente
    units_pending: Mapped[bool] = mapped_column(Boolean, default=False)
    category: Mapped[str | None] = mapped_column(String(60))
    expense_type: Mapped[str | None] = mapped_column(String(12))       # fijo | variable
    counterparty: Mapped[str | None] = mapped_column(String(80))
    description: Mapped[str | None] = mapped_column(Text)
    raw_text: Mapped[str | None] = mapped_column(Text)
    channel: Mapped[str | None] = mapped_column(String(12))            # web | whatsapp | app | demo
    origin: Mapped[str] = mapped_column(String(24), default="autodeclarado")  # autodeclarado | con_adjunto | respaldo_yape | comprobante
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("movements.id"))
    goal_id: Mapped[int | None] = mapped_column(ForeignKey("goals.id"))
    debt_id: Mapped[int | None] = mapped_column(ForeignKey("debts.id"))
    status: Mapped[str] = mapped_column(String(12), default="confirmado")  # confirmado | anulado
    revision: Mapped[int] = mapped_column(Integer, default=1)
    demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_lima)

    product: Mapped[Product | None] = relationship()
    cash_entries: Mapped[list[CashEntry]] = relationship(back_populates="movement", cascade="all, delete-orphan")
    stock_entries: Mapped[list[StockEntry]] = relationship(back_populates="movement", cascade="all, delete-orphan")
    attachments: Mapped[list[Attachment]] = relationship(back_populates="movement", cascade="all, delete-orphan")


class CashEntry(Base):
    """Línea de caja: cada movimiento genera sus efectos en el mismo commit."""
    __tablename__ = "cash_entries"
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    movement_id: Mapped[int] = mapped_column(ForeignKey("movements.id", ondelete="CASCADE"), index=True)
    pocket: Mapped[str] = mapped_column(String(16))   # efectivo | yape | ahorro
    delta_cents: Mapped[int] = mapped_column(Integer)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    movement: Mapped[Movement] = relationship(back_populates="cash_entries")


class StockEntry(Base):
    __tablename__ = "stock_entries"
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    movement_id: Mapped[int] = mapped_column(ForeignKey("movements.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    delta_qty: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(20))   # compra | venta | merma | devolucion | ajuste
    occurred_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    movement: Mapped[Movement] = relationship(back_populates="stock_entries")


class MovementRevision(Base):
    __tablename__ = "movement_revisions"
    id: Mapped[int] = mapped_column(primary_key=True)
    movement_id: Mapped[int] = mapped_column(ForeignKey("movements.id", ondelete="CASCADE"), index=True)
    changed_at: Mapped[datetime] = mapped_column(DateTime, default=now_lima)
    before: Mapped[dict] = mapped_column(JSON)
    after: Mapped[dict] = mapped_column(JSON)
    reason: Mapped[str | None] = mapped_column(Text)


class Attachment(Base):
    __tablename__ = "attachments"
    id: Mapped[int] = mapped_column(primary_key=True)
    movement_id: Mapped[int] = mapped_column(ForeignKey("movements.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(30))   # comprobante_proveedor | captura_yape | otro
    filename: Mapped[str] = mapped_column(String(200))
    demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_lima)
    movement: Mapped[Movement] = relationship(back_populates="attachments")


class YapePayment(Base):
    """Notificación de cobro Yape (en el MVP: datos de demostración importados)."""
    __tablename__ = "yape_payments"
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    payer: Mapped[str] = mapped_column(String(80))
    amount_cents: Mapped[int] = mapped_column(Integer)
    received_at: Mapped[datetime] = mapped_column(DateTime)
    operation_code: Mapped[str] = mapped_column(String(40))
    movement_id: Mapped[int | None] = mapped_column(ForeignKey("movements.id", ondelete="SET NULL"))
    demo: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (UniqueConstraint("business_id", "operation_code"),)


class Count(Base):
    """Conteo autodeclarado de stock o caja y resultado del cruce."""
    __tablename__ = "counts"
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(10))   # stock | caja
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"))
    pocket: Mapped[str | None] = mapped_column(String(12))
    counted: Mapped[int] = mapped_column(Integer)          # unidades o céntimos
    expected: Mapped[int | None] = mapped_column(Integer)
    difference: Mapped[int | None] = mapped_column(Integer)
    result: Mapped[str] = mapped_column(String(20))        # consistente | diferencia | sin_datos
    review_status: Mapped[str] = mapped_column(String(20), default="abierto")  # abierto | pendiente | revisado | ajustado
    note: Mapped[str | None] = mapped_column(Text)
    counted_at: Mapped[datetime] = mapped_column(DateTime, default=now_lima)
    demo: Mapped[bool] = mapped_column(Boolean, default=False)


class FixedExpense(Base):
    __tablename__ = "fixed_expenses"
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(60))
    amount_cents: Mapped[int] = mapped_column(Integer)
    due_day: Mapped[int] = mapped_column(Integer, default=1)


class Debt(Base):
    __tablename__ = "debts"
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    creditor: Mapped[str] = mapped_column(String(80))
    total_cents: Mapped[int] = mapped_column(Integer)
    installment_cents: Mapped[int] = mapped_column(Integer)
    due_day: Mapped[int] = mapped_column(Integer, default=15)
    installments_total: Mapped[int | None] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Asset(Base):
    __tablename__ = "assets"
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    value_cents: Mapped[int] = mapped_column(Integer)


class Goal(Base):
    __tablename__ = "goals"
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(12))   # reposicion | ahorro
    name: Mapped[str] = mapped_column(String(80))
    target_cents: Mapped[int] = mapped_column(Integer)
    deadline: Mapped[date | None] = mapped_column(Date)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"))
    quantity: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(12), default="activa")  # activa | cumplida | cancelada
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_lima)


class Draft(Base):
    """Borrador de un movimiento que espera aclaración o confirmación."""
    __tablename__ = "drafts"
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    conversation: Mapped[str] = mapped_column(String(80), index=True)
    op_id: Mapped[str] = mapped_column(String(64), unique=True)
    action: Mapped[str] = mapped_column(String(20))   # movimiento | correccion | anulacion | catalogo | meta | saldo | conteo | consentimiento
    data: Mapped[dict[str, Any]] = mapped_column(JSON)
    missing: Mapped[str | None] = mapped_column(String(30))   # campo por el que se preguntó
    options: Mapped[list | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(12), default="abierto")  # abierto | confirmado | cancelado
    summary_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_lima)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now_lima, onupdate=now_lima)


class ProcessedMessage(Base):
    """Idempotencia de mensajes entrantes (web, audio pendiente, WhatsApp)."""
    __tablename__ = "processed_messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[str] = mapped_column(String(128), unique=True)
    business_id: Mapped[int | None] = mapped_column(Integer)
    channel: Mapped[str] = mapped_column(String(12))
    text: Mapped[str | None] = mapped_column(Text)
    response: Mapped[dict] = mapped_column(JSON)
    received_at: Mapped[datetime] = mapped_column(DateTime, default=now_lima)


class ChatLog(Base):
    __tablename__ = "chat_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(10))  # user | bot
    text: Mapped[str] = mapped_column(Text)
    channel: Mapped[str] = mapped_column(String(12), default="web")
    via_voice: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_lima)


class ReportConsent(Base):
    """Cada mes se pregunta si desea enviar su informe al BCP (envío simulado en el MVP)."""
    __tablename__ = "report_consents"
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    month: Mapped[str] = mapped_column(String(7))   # YYYY-MM del periodo informado
    decision: Mapped[str] = mapped_column(String(10))  # si | no
    decided_at: Mapped[datetime] = mapped_column(DateTime, default=now_lima)
    __table_args__ = (UniqueConstraint("business_id", "month"),)
