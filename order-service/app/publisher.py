from saga_shared.events import EventEnvelope, EventType, OrderCreatedPayload
from saga_shared.rabbitmq import Publisher


class OrderEventPublisher:
    def __init__(self, publisher: Publisher):
        self._publisher = publisher

    async def order_created(self, payload: OrderCreatedPayload) -> None:
        envelope = EventEnvelope.create(EventType.ORDER_CREATED, payload)
        await self._publisher.publish(EventType.ORDER_CREATED, envelope)
