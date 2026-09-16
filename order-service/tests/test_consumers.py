import pytest

from saga_shared.events import (
    EventEnvelope,
    EventType,
    InventoryReleasedPayload,
    InventoryReservationFailedPayload,
    InventoryReservedPayload,
    OrderItem,
    PaymentCompletedPayload,
    PaymentFailedPayload,
)

from app.consumers import OrderConsumerHandlers
from app.models import FailureReason, OrderStatus
from app.repository import OrderRepository


@pytest.fixture
def repo(db):
    return OrderRepository(db)


@pytest.fixture
def handlers(db, repo):
    return OrderConsumerHandlers(db, repo)


def _raw(event_type: str, payload) -> dict:
    return EventEnvelope.create(event_type, payload).model_dump(mode="json")


@pytest.mark.asyncio
async def test_on_inventory_reserved_transitions_order(repo, handlers):
    doc = await repo.create_order("cust-1", [{"sku": "SKU-1", "qty": 1}], 1000, False, 0)
    order_id = doc["_id"]

    raw = _raw(
        EventType.INVENTORY_RESERVED,
        InventoryReservedPayload(
            order_id=order_id,
            reservation_id="res-1",
            items=[OrderItem(sku="SKU-1", qty=1)],
            amount_cents=1000,
        ),
    )
    await handlers.on_inventory_reserved(raw)

    updated = await repo.get_order(order_id)
    assert updated["status"] == OrderStatus.INVENTORY_RESERVED.value


@pytest.mark.asyncio
async def test_on_inventory_reserved_is_idempotent_on_redelivery(repo, handlers):
    doc = await repo.create_order("cust-1", [{"sku": "SKU-1", "qty": 1}], 1000, False, 0)
    order_id = doc["_id"]

    raw = _raw(
        EventType.INVENTORY_RESERVED,
        InventoryReservedPayload(
            order_id=order_id,
            reservation_id="res-1",
            items=[OrderItem(sku="SKU-1", qty=1)],
            amount_cents=1000,
        ),
    )
    await handlers.on_inventory_reserved(raw)
    # Simulate RabbitMQ redelivering the exact same message (same event_id).
    await handlers.on_inventory_reserved(raw)

    updated = await repo.get_order(order_id)
    # Only one INVENTORY_RESERVED entry should have been appended to history.
    reserved_entries = [h for h in updated["history"] if h["status"] == OrderStatus.INVENTORY_RESERVED.value]
    assert len(reserved_entries) == 1


@pytest.mark.asyncio
async def test_on_inventory_reservation_failed_marks_order_failed(repo, handlers):
    doc = await repo.create_order("cust-1", [{"sku": "SKU-1", "qty": 5}], 1000, False, 0)
    order_id = doc["_id"]

    raw = _raw(
        EventType.INVENTORY_RESERVATION_FAILED,
        InventoryReservationFailedPayload(
            order_id=order_id, reason="not enough stock", items_unavailable=["SKU-1"]
        ),
    )
    await handlers.on_inventory_reservation_failed(raw)

    updated = await repo.get_order(order_id)
    assert updated["status"] == OrderStatus.FAILED.value
    assert updated["failure_reason"] == FailureReason.INSUFFICIENT_STOCK.value


@pytest.mark.asyncio
async def test_on_payment_completed_confirms_order(repo, handlers):
    doc = await repo.create_order("cust-1", [{"sku": "SKU-1", "qty": 1}], 1000, False, 0)
    order_id = doc["_id"]
    await repo.transition_status(order_id, OrderStatus.INVENTORY_RESERVED)

    raw = _raw(
        EventType.PAYMENT_COMPLETED,
        PaymentCompletedPayload(order_id=order_id, payment_id="pay-1", amount_cents=1000),
    )
    await handlers.on_payment_completed(raw)

    updated = await repo.get_order(order_id)
    assert updated["status"] == OrderStatus.CONFIRMED.value


@pytest.mark.asyncio
async def test_on_payment_failed_marks_order_failed_with_reason(repo, handlers):
    doc = await repo.create_order("cust-1", [{"sku": "SKU-1", "qty": 1}], 150000, False, 0)
    order_id = doc["_id"]
    await repo.transition_status(order_id, OrderStatus.INVENTORY_RESERVED)

    raw = _raw(
        EventType.PAYMENT_FAILED,
        PaymentFailedPayload(order_id=order_id, payment_id="pay-1", reason="over threshold"),
    )
    await handlers.on_payment_failed(raw)

    updated = await repo.get_order(order_id)
    assert updated["status"] == OrderStatus.FAILED.value
    assert updated["failure_reason"] == FailureReason.PAYMENT_DECLINED.value


@pytest.mark.asyncio
async def test_on_inventory_released_appends_audit_without_changing_status(repo, handlers):
    doc = await repo.create_order("cust-1", [{"sku": "SKU-1", "qty": 1}], 150000, False, 0)
    order_id = doc["_id"]
    await repo.transition_status(order_id, OrderStatus.FAILED, FailureReason.PAYMENT_DECLINED)

    raw = _raw(
        EventType.INVENTORY_RELEASED,
        InventoryReleasedPayload(order_id=order_id, reservation_id="res-1"),
    )
    await handlers.on_inventory_released(raw)

    updated = await repo.get_order(order_id)
    assert updated["status"] == OrderStatus.FAILED.value
    assert updated["history"][-1]["status"] == "INVENTORY_RELEASED"
