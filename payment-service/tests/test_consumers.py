import pytest

from saga_shared.events import EventEnvelope, EventType, InventoryReservedPayload, OrderItem

from app.consumers import PaymentConsumerHandlers
from app.repository import PaymentRepository

THRESHOLD_CENTS = 100_000


class FakePublisher:
    def __init__(self):
        self.completed_calls = []
        self.failed_calls = []

    async def payment_completed(self, order_id, payment_id, amount_cents):
        self.completed_calls.append((order_id, payment_id, amount_cents))

    async def payment_failed(self, order_id, payment_id, reason):
        self.failed_calls.append((order_id, payment_id, reason))


@pytest.fixture
def repo(db):
    return PaymentRepository(db)


@pytest.fixture
def publisher():
    return FakePublisher()


@pytest.fixture
def handlers(db, repo, publisher):
    return PaymentConsumerHandlers(db, repo, publisher, THRESHOLD_CENTS)


def _reserved_raw(order_id: str, amount_cents: int, force_payment_failure: bool = False) -> dict:
    payload = InventoryReservedPayload(
        order_id=order_id,
        reservation_id="res-1",
        items=[OrderItem(sku="SKU-1", qty=1)],
        amount_cents=amount_cents,
        force_payment_failure=force_payment_failure,
    )
    return EventEnvelope.create(EventType.INVENTORY_RESERVED, payload).model_dump(mode="json")


@pytest.mark.asyncio
async def test_on_inventory_reserved_completes_payment_under_threshold(handlers, publisher, repo):
    await handlers.on_inventory_reserved(_reserved_raw("order-1", 50_000))

    assert len(publisher.completed_calls) == 1
    assert publisher.failed_calls == []
    payments = await repo.list_payments()
    assert payments[0]["status"] == "COMPLETED"


@pytest.mark.asyncio
async def test_on_inventory_reserved_declines_payment_over_threshold(handlers, publisher, repo):
    await handlers.on_inventory_reserved(_reserved_raw("order-1", 150_000))

    assert publisher.completed_calls == []
    assert len(publisher.failed_calls) == 1
    payments = await repo.list_payments()
    assert payments[0]["status"] == "DECLINED"


@pytest.mark.asyncio
async def test_on_inventory_reserved_honors_forced_failure(handlers, publisher):
    await handlers.on_inventory_reserved(_reserved_raw("order-1", 100, force_payment_failure=True))

    assert publisher.completed_calls == []
    assert len(publisher.failed_calls) == 1


@pytest.mark.asyncio
async def test_on_inventory_reserved_is_idempotent_on_redelivery(handlers, publisher):
    raw = _reserved_raw("order-1", 50_000)
    await handlers.on_inventory_reserved(raw)
    await handlers.on_inventory_reserved(raw)

    assert len(publisher.completed_calls) == 1
