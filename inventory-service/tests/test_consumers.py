import pytest

from saga_shared.events import (
    EventEnvelope,
    EventType,
    OrderCreatedPayload,
    OrderItem,
    PaymentFailedPayload,
)

from app.consumers import InventoryConsumerHandlers, TransientDemoFailure
from app.repository import ReservationRepository, StockRepository
from app.seed import SEED_STOCK


class FakePublisher:
    def __init__(self):
        self.reserved_calls = []
        self.reservation_failed_calls = []
        self.released_calls = []

    async def inventory_reserved(self, order_id, reservation_id, items, amount_cents, force_payment_failure):
        self.reserved_calls.append((order_id, reservation_id, items, amount_cents, force_payment_failure))

    async def inventory_reservation_failed(self, order_id, reason, items_unavailable):
        self.reservation_failed_calls.append((order_id, reason, items_unavailable))

    async def inventory_released(self, order_id, reservation_id):
        self.released_calls.append((order_id, reservation_id))


@pytest.fixture
async def stock_repo(db):
    repo = StockRepository(db)
    await repo.seed_if_empty(SEED_STOCK)
    return repo


@pytest.fixture
def reservation_repo(db):
    return ReservationRepository(db)


@pytest.fixture
def publisher():
    return FakePublisher()


@pytest.fixture
def handlers(db, stock_repo, reservation_repo, publisher):
    return InventoryConsumerHandlers(db, stock_repo, reservation_repo, publisher)


def _order_created_raw(order_id: str, sku: str, qty: int, **overrides) -> dict:
    payload = OrderCreatedPayload(
        order_id=order_id,
        customer_id="cust-1",
        items=[OrderItem(sku=sku, qty=qty)],
        amount_cents=1000,
        **overrides,
    )
    return EventEnvelope.create(EventType.ORDER_CREATED, payload).model_dump(mode="json")


@pytest.mark.asyncio
async def test_on_order_created_reserves_and_publishes_reserved(handlers, publisher, stock_repo):
    raw = _order_created_raw("order-1", "SKU-1", 5)
    await handlers.on_order_created(raw)

    assert len(publisher.reserved_calls) == 1
    assert publisher.reserved_calls[0][0] == "order-1"

    stock = {doc["_id"]: doc for doc in await stock_repo.list_stock()}
    assert stock["SKU-1"]["available_qty"] == 95


@pytest.mark.asyncio
async def test_on_order_created_publishes_reservation_failed_when_out_of_stock(handlers, publisher):
    raw = _order_created_raw("order-1", "SKU-5", 5)  # only 2 units seeded
    await handlers.on_order_created(raw)

    assert publisher.reserved_calls == []
    assert len(publisher.reservation_failed_calls) == 1
    assert publisher.reservation_failed_calls[0][0] == "order-1"


@pytest.mark.asyncio
async def test_on_order_created_is_idempotent_on_redelivery(handlers, publisher):
    raw = _order_created_raw("order-1", "SKU-1", 5)
    await handlers.on_order_created(raw)
    await handlers.on_order_created(raw)  # simulated redelivery, same event_id

    assert len(publisher.reserved_calls) == 1


@pytest.mark.asyncio
async def test_chaos_knob_raises_until_attempts_exhausted(handlers, publisher):
    raw = _order_created_raw("order-1", "SKU-1", 5, simulate_transient_failure_count=2)

    with pytest.raises(TransientDemoFailure):
        await handlers.on_order_created(raw)
    with pytest.raises(TransientDemoFailure):
        await handlers.on_order_created(raw)

    # Third attempt (as ResilientConsumer would redeliver from the retry
    # queue) should go through and actually reserve stock.
    await handlers.on_order_created(raw)
    assert len(publisher.reserved_calls) == 1


@pytest.mark.asyncio
async def test_on_payment_failed_releases_reservation_and_publishes_released(
    handlers, publisher, stock_repo, reservation_repo
):
    await handlers.on_order_created(_order_created_raw("order-1", "SKU-1", 5))
    reservation = await reservation_repo.get_by_order_id("order-1")

    payload = PaymentFailedPayload(order_id="order-1", payment_id="pay-1", reason="declined")
    raw = EventEnvelope.create(EventType.PAYMENT_FAILED, payload).model_dump(mode="json")
    await handlers.on_payment_failed(raw)

    assert publisher.released_calls == [("order-1", reservation["_id"])]
    stock = {doc["_id"]: doc for doc in await stock_repo.list_stock()}
    assert stock["SKU-1"]["available_qty"] == 100


@pytest.mark.asyncio
async def test_on_payment_failed_is_noop_when_no_reservation_exists(handlers, publisher):
    # e.g. the order already short-circuited on insufficient stock, so
    # payment-service never even ran - nothing to compensate here.
    payload = PaymentFailedPayload(order_id="order-never-reserved", payment_id="pay-1", reason="declined")
    raw = EventEnvelope.create(EventType.PAYMENT_FAILED, payload).model_dump(mode="json")
    await handlers.on_payment_failed(raw)

    assert publisher.released_calls == []
