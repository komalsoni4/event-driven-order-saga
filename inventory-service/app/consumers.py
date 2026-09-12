from __future__ import annotations

import logging

from saga_shared.events import EventEnvelope, OrderCreatedPayload, PaymentFailedPayload
from saga_shared.idempotency import try_mark_processed
from saga_shared.rabbitmq import ResilientConsumer

from .publisher import InventoryEventPublisher
from .repository import ReservationRepository, StockRepository, consume_chaos_attempt

logger = logging.getLogger(__name__)

QUEUE_ORDER_CREATED = "inventory-service.order.created"
ROUTING_ORDER_CREATED = "order.created"

QUEUE_PAYMENT_FAILED = "inventory-service.payment.failed"
ROUTING_PAYMENT_FAILED = "payment.failed"


class TransientDemoFailure(RuntimeError):
    """Raised deliberately by the chaos knob so ResilientConsumer's
    retry/backoff path has something real to demo on command."""


class InventoryConsumerHandlers:
    def __init__(
        self,
        db,
        stock_repo: StockRepository,
        reservation_repo: ReservationRepository,
        publisher: InventoryEventPublisher,
    ):
        self._db = db
        self._stock_repo = stock_repo
        self._reservation_repo = reservation_repo
        self._publisher = publisher

    async def on_order_created(self, raw: dict) -> None:
        envelope = EventEnvelope.model_validate(raw)
        data = OrderCreatedPayload.model_validate(envelope.payload)

        # Chaos gate runs before the idempotency mark so a deliberately
        # injected failure actually gets retried by ResilientConsumer instead
        # of being swallowed as a "duplicate" on redelivery.
        if await consume_chaos_attempt(
            self._db, envelope.event_id, data.simulate_transient_failure_count
        ):
            raise TransientDemoFailure(
                f"simulated transient failure for order {data.order_id}"
            )

        if not await try_mark_processed(self._db, envelope.event_id, envelope.event_type):
            return

        items = [item.model_dump() for item in data.items]
        success, unavailable = await self._stock_repo.reserve_items(items)
        if success:
            reservation = await self._reservation_repo.create(data.order_id, items)
            await self._publisher.inventory_reserved(
                data.order_id,
                reservation["_id"],
                data.items,
                data.amount_cents,
                data.force_payment_failure,
            )
        else:
            await self._publisher.inventory_reservation_failed(
                data.order_id,
                reason=f"insufficient stock for {', '.join(unavailable)}",
                items_unavailable=unavailable,
            )

    async def on_payment_failed(self, raw: dict) -> None:
        envelope = EventEnvelope.model_validate(raw)
        if not await try_mark_processed(self._db, envelope.event_id, envelope.event_type):
            return
        data = PaymentFailedPayload.model_validate(envelope.payload)

        reservation = await self._reservation_repo.get_by_order_id(data.order_id)
        if reservation is None or reservation["status"] == "RELEASED":
            # Nothing to compensate: either the order never reached a
            # reservation (short-circuited on insufficient stock earlier) or
            # it was already released by a previous delivery of this event.
            return

        await self._stock_repo.release_items(reservation["items"])
        await self._reservation_repo.mark_released(reservation["_id"])
        await self._publisher.inventory_released(data.order_id, reservation["_id"])


def build_consumers(
    channel, handlers: InventoryConsumerHandlers, max_retries: int, base_delay_ms: int
) -> list[ResilientConsumer]:
    specs = [
        (QUEUE_ORDER_CREATED, ROUTING_ORDER_CREATED, handlers.on_order_created),
        (QUEUE_PAYMENT_FAILED, ROUTING_PAYMENT_FAILED, handlers.on_payment_failed),
    ]
    return [
        ResilientConsumer(channel, queue_name, routing_key, handler, max_retries, base_delay_ms)
        for queue_name, routing_key, handler in specs
    ]
