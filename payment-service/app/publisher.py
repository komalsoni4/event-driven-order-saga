from saga_shared.events import EventEnvelope, EventType, PaymentCompletedPayload, PaymentFailedPayload
from saga_shared.rabbitmq import Publisher


class PaymentEventPublisher:
    def __init__(self, publisher: Publisher):
        self._publisher = publisher

    async def payment_completed(self, order_id: str, payment_id: str, amount_cents: int) -> None:
        payload = PaymentCompletedPayload(order_id=order_id, payment_id=payment_id, amount_cents=amount_cents)
        envelope = EventEnvelope.create(EventType.PAYMENT_COMPLETED, payload)
        await self._publisher.publish(EventType.PAYMENT_COMPLETED, envelope)

    async def payment_failed(self, order_id: str, payment_id: str, reason: str) -> None:
        payload = PaymentFailedPayload(order_id=order_id, payment_id=payment_id, reason=reason)
        envelope = EventEnvelope.create(EventType.PAYMENT_FAILED, payload)
        await self._publisher.publish(EventType.PAYMENT_FAILED, envelope)
