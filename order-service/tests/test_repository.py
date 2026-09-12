import pytest

from app.models import FailureReason, OrderStatus
from app.repository import OrderRepository


@pytest.fixture
def repo(db):
    return OrderRepository(db)


@pytest.mark.asyncio
async def test_create_order_starts_pending(repo):
    doc = await repo.create_order(
        customer_id="cust-1",
        items=[{"sku": "SKU-1", "qty": 2}],
        amount_cents=5000,
        force_payment_failure=False,
        simulate_transient_failure_count=0,
    )
    assert doc["status"] == OrderStatus.PENDING.value
    assert len(doc["history"]) == 1
    assert doc["history"][0]["status"] == OrderStatus.PENDING.value


@pytest.mark.asyncio
async def test_transition_status_updates_and_appends_history(repo):
    doc = await repo.create_order("cust-1", [{"sku": "SKU-1", "qty": 1}], 1000, False, 0)
    order_id = doc["_id"]

    applied = await repo.transition_status(order_id, OrderStatus.INVENTORY_RESERVED)
    assert applied is True

    updated = await repo.get_order(order_id)
    assert updated["status"] == OrderStatus.INVENTORY_RESERVED.value
    assert [h["status"] for h in updated["history"]] == [
        OrderStatus.PENDING.value,
        OrderStatus.INVENTORY_RESERVED.value,
    ]


@pytest.mark.asyncio
async def test_transition_status_sets_failure_reason(repo):
    doc = await repo.create_order("cust-1", [{"sku": "SKU-1", "qty": 1}], 1000, False, 0)
    order_id = doc["_id"]

    await repo.transition_status(order_id, OrderStatus.FAILED, FailureReason.INSUFFICIENT_STOCK)

    updated = await repo.get_order(order_id)
    assert updated["status"] == OrderStatus.FAILED.value
    assert updated["failure_reason"] == FailureReason.INSUFFICIENT_STOCK.value


@pytest.mark.asyncio
async def test_transition_status_is_ignored_once_order_is_terminal(repo):
    doc = await repo.create_order("cust-1", [{"sku": "SKU-1", "qty": 1}], 1000, False, 0)
    order_id = doc["_id"]

    await repo.transition_status(order_id, OrderStatus.FAILED, FailureReason.PAYMENT_DECLINED)

    # A stale/late event (e.g. a retried inventory.reserved) must not resurrect
    # an order that's already reached a terminal state.
    applied = await repo.transition_status(order_id, OrderStatus.INVENTORY_RESERVED)
    assert applied is False

    unchanged = await repo.get_order(order_id)
    assert unchanged["status"] == OrderStatus.FAILED.value


@pytest.mark.asyncio
async def test_append_audit_does_not_change_status(repo):
    doc = await repo.create_order("cust-1", [{"sku": "SKU-1", "qty": 1}], 1000, False, 0)
    order_id = doc["_id"]
    await repo.transition_status(order_id, OrderStatus.FAILED, FailureReason.PAYMENT_DECLINED)

    await repo.append_audit(order_id, "INVENTORY_RELEASED")

    updated = await repo.get_order(order_id)
    assert updated["status"] == OrderStatus.FAILED.value
    assert updated["history"][-1]["status"] == "INVENTORY_RELEASED"
