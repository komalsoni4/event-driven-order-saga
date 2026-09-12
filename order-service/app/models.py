from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel

from saga_shared.events import OrderItem


class OrderStatus(StrEnum):
    PENDING = "PENDING"
    INVENTORY_RESERVED = "INVENTORY_RESERVED"
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"


class FailureReason(StrEnum):
    INSUFFICIENT_STOCK = "INSUFFICIENT_STOCK"
    PAYMENT_DECLINED = "PAYMENT_DECLINED"


class CreateOrderRequest(BaseModel):
    customer_id: str
    items: list[OrderItem]
    amount_cents: int
    force_payment_failure: bool = False
    simulate_transient_failure_count: int = 0


class HistoryEntry(BaseModel):
    status: str
    at: datetime


class OrderResponse(BaseModel):
    order_id: str
    customer_id: str
    items: list[OrderItem]
    amount_cents: int
    status: OrderStatus
    failure_reason: FailureReason | None = None
    history: list[HistoryEntry]
    created_at: datetime
    updated_at: datetime
