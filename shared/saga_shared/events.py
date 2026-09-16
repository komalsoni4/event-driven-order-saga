"""Event schemas shared by every service in the saga.

Every event that crosses RabbitMQ is an ``EventEnvelope`` whose ``payload`` is
the ``model_dump()`` of one of the payload models below. Publishers build the
envelope; consumers parse the envelope, then re-validate ``payload`` against
the payload model they expect for that routing key.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from .observability import get_correlation_id


class EventType:
    ORDER_CREATED = "order.created"
    INVENTORY_RESERVED = "inventory.reserved"
    INVENTORY_RESERVATION_FAILED = "inventory.reservation_failed"
    PAYMENT_COMPLETED = "payment.completed"
    PAYMENT_FAILED = "payment.failed"
    INVENTORY_RELEASED = "inventory.released"


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class EventEnvelope(BaseModel):
    event_id: str = Field(default_factory=new_id)
    correlation_id: str = Field(default_factory=lambda: get_correlation_id() or new_id())
    event_type: str
    occurred_at: datetime = Field(default_factory=utcnow)
    payload: dict[str, Any]

    @classmethod
    def create(cls, event_type: str, payload: BaseModel) -> "EventEnvelope":
        return cls(
            event_type=event_type,
            correlation_id=get_correlation_id() or new_id(),
            payload=payload.model_dump(mode="json"),
        )


class OrderItem(BaseModel):
    sku: str
    qty: int


class OrderCreatedPayload(BaseModel):
    order_id: str
    customer_id: str
    items: list[OrderItem]
    amount_cents: int
    force_payment_failure: bool = False
    simulate_transient_failure_count: int = 0


class InventoryReservedPayload(BaseModel):
    order_id: str
    reservation_id: str
    items: list[OrderItem]
    amount_cents: int
    force_payment_failure: bool = False


class InventoryReservationFailedPayload(BaseModel):
    order_id: str
    reason: str
    items_unavailable: list[str]


class PaymentCompletedPayload(BaseModel):
    order_id: str
    payment_id: str
    amount_cents: int


class PaymentFailedPayload(BaseModel):
    order_id: str
    payment_id: str
    reason: str


class InventoryReleasedPayload(BaseModel):
    order_id: str
    reservation_id: str
