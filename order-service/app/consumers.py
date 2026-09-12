"""order-service's consumers.

Handlers are plain async functions on ``OrderConsumerHandlers`` that take the
raw decoded message dict and an injected repo/db - no channel, no broker
involved - so they're directly unit-testable. ``build_consumers`` is the only
place that wires them up to real queues via ``ResilientConsumer``.
"""
from __future__ import annotations

import logging

from saga_shared.events import (
    EventEnvelope,
    InventoryReleasedPayload,
    InventoryReservationFailedPayload,
    InventoryReservedPayload,
    PaymentCompletedPayload,
    PaymentFailedPayload,
)
from saga_shared.idempotency import try_mark_processed
from saga_shared.rabbitmq import ResilientConsumer

from .models import FailureReason, OrderStatus
from .repository import OrderRepository

logger = logging.getLogger(__name__)

QUEUE_INVENTORY_RESERVED = "order-service.inventory.reserved"
ROUTING_INVENTORY_RESERVED = "inventory.reserved"

QUEUE_INVENTORY_RESERVATION_FAILED = "order-service.inventory.reservation_failed"
ROUTING_INVENTORY_RESERVATION_FAILED = "inventory.reservation_failed"

QUEUE_PAYMENT_COMPLETED = "order-service.payment.completed"
ROUTING_PAYMENT_COMPLETED = "payment.completed"

QUEUE_PAYMENT_FAILED = "order-service.payment.failed"
ROUTING_PAYMENT_FAILED = "payment.failed"

QUEUE_INVENTORY_RELEASED = "order-service.inventory.released"
ROUTING_INVENTORY_RELEASED = "inventory.released"


class OrderConsumerHandlers:
    def __init__(self, db, repo: OrderRepository):
        self._db = db
        self._repo = repo

    async def _dedup(self, envelope: EventEnvelope) -> bool:
        return await try_mark_processed(self._db, envelope.event_id, envelope.event_type)

    async def on_inventory_reserved(self, raw: dict) -> None:
        envelope = EventEnvelope.model_validate(raw)
        if not await self._dedup(envelope):
            return
        data = InventoryReservedPayload.model_validate(envelope.payload)
        await self._repo.transition_status(data.order_id, OrderStatus.INVENTORY_RESERVED)

    async def on_inventory_reservation_failed(self, raw: dict) -> None:
        envelope = EventEnvelope.model_validate(raw)
        if not await self._dedup(envelope):
            return
        data = InventoryReservationFailedPayload.model_validate(envelope.payload)
        await self._repo.transition_status(
            data.order_id, OrderStatus.FAILED, FailureReason.INSUFFICIENT_STOCK
        )

    async def on_payment_completed(self, raw: dict) -> None:
        envelope = EventEnvelope.model_validate(raw)
        if not await self._dedup(envelope):
            return
        data = PaymentCompletedPayload.model_validate(envelope.payload)
        await self._repo.transition_status(data.order_id, OrderStatus.CONFIRMED)

    async def on_payment_failed(self, raw: dict) -> None:
        envelope = EventEnvelope.model_validate(raw)
        if not await self._dedup(envelope):
            return
        data = PaymentFailedPayload.model_validate(envelope.payload)
        await self._repo.transition_status(
            data.order_id, OrderStatus.FAILED, FailureReason.PAYMENT_DECLINED
        )

    async def on_inventory_released(self, raw: dict) -> None:
        envelope = EventEnvelope.model_validate(raw)
        if not await self._dedup(envelope):
            return
        data = InventoryReleasedPayload.model_validate(envelope.payload)
        await self._repo.append_audit(data.order_id, "INVENTORY_RELEASED")


def build_consumers(
    channel, handlers: OrderConsumerHandlers, max_retries: int, base_delay_ms: int
) -> list[ResilientConsumer]:
    specs = [
        (QUEUE_INVENTORY_RESERVED, ROUTING_INVENTORY_RESERVED, handlers.on_inventory_reserved),
        (
            QUEUE_INVENTORY_RESERVATION_FAILED,
            ROUTING_INVENTORY_RESERVATION_FAILED,
            handlers.on_inventory_reservation_failed,
        ),
        (QUEUE_PAYMENT_COMPLETED, ROUTING_PAYMENT_COMPLETED, handlers.on_payment_completed),
        (QUEUE_PAYMENT_FAILED, ROUTING_PAYMENT_FAILED, handlers.on_payment_failed),
        (QUEUE_INVENTORY_RELEASED, ROUTING_INVENTORY_RELEASED, handlers.on_inventory_released),
    ]
    return [
        ResilientConsumer(channel, queue_name, routing_key, handler, max_retries, base_delay_ms)
        for queue_name, routing_key, handler in specs
    ]
