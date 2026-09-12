from saga_shared.events import (
    EventEnvelope,
    EventType,
    InventoryReleasedPayload,
    InventoryReservationFailedPayload,
    InventoryReservedPayload,
    OrderItem,
)
from saga_shared.rabbitmq import Publisher


class InventoryEventPublisher:
    def __init__(self, publisher: Publisher):
        self._publisher = publisher

    async def inventory_reserved(
        self,
        order_id: str,
        reservation_id: str,
        items: list[OrderItem],
        amount_cents: int,
        force_payment_failure: bool,
    ) -> None:
        payload = InventoryReservedPayload(
            order_id=order_id,
            reservation_id=reservation_id,
            items=items,
            amount_cents=amount_cents,
            force_payment_failure=force_payment_failure,
        )
        envelope = EventEnvelope.create(EventType.INVENTORY_RESERVED, payload)
        await self._publisher.publish(EventType.INVENTORY_RESERVED, envelope)

    async def inventory_reservation_failed(
        self, order_id: str, reason: str, items_unavailable: list[str]
    ) -> None:
        payload = InventoryReservationFailedPayload(
            order_id=order_id, reason=reason, items_unavailable=items_unavailable
        )
        envelope = EventEnvelope.create(EventType.INVENTORY_RESERVATION_FAILED, payload)
        await self._publisher.publish(EventType.INVENTORY_RESERVATION_FAILED, envelope)

    async def inventory_released(self, order_id: str, reservation_id: str) -> None:
        payload = InventoryReleasedPayload(order_id=order_id, reservation_id=reservation_id)
        envelope = EventEnvelope.create(EventType.INVENTORY_RELEASED, payload)
        await self._publisher.publish(EventType.INVENTORY_RELEASED, envelope)
