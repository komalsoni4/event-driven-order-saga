from __future__ import annotations

import logging

from saga_shared.events import EventEnvelope, InventoryReservedPayload
from saga_shared.idempotency import try_mark_processed
from saga_shared.rabbitmq import ResilientConsumer

from .publisher import PaymentEventPublisher
from .repository import PaymentRepository
from .simulator import decide_payment_outcome

logger = logging.getLogger(__name__)

QUEUE_INVENTORY_RESERVED = "payment-service.inventory.reserved"
ROUTING_INVENTORY_RESERVED = "inventory.reserved"


class PaymentConsumerHandlers:
    def __init__(
        self,
        db,
        repo: PaymentRepository,
        publisher: PaymentEventPublisher,
        threshold_cents: int,
    ):
        self._db = db
        self._repo = repo
        self._publisher = publisher
        self._threshold_cents = threshold_cents

    async def on_inventory_reserved(self, raw: dict) -> None:
        envelope = EventEnvelope.model_validate(raw)
        if not await try_mark_processed(self._db, envelope.event_id, envelope.event_type):
            return
        data = InventoryReservedPayload.model_validate(envelope.payload)

        approved, reason = decide_payment_outcome(
            data.amount_cents, data.force_payment_failure, self._threshold_cents
        )
        status = "COMPLETED" if approved else "DECLINED"
        payment = await self._repo.create(data.order_id, data.amount_cents, status, reason)

        if approved:
            await self._publisher.payment_completed(
                data.order_id, payment["_id"], data.amount_cents
            )
        else:
            await self._publisher.payment_failed(data.order_id, payment["_id"], reason or "declined")


def build_consumers(
    channel, handlers: PaymentConsumerHandlers, max_retries: int, base_delay_ms: int
) -> list[ResilientConsumer]:
    return [
        ResilientConsumer(
            channel,
            QUEUE_INVENTORY_RESERVED,
            ROUTING_INVENTORY_RESERVED,
            handlers.on_inventory_reserved,
            max_retries,
            base_delay_ms,
        )
    ]
