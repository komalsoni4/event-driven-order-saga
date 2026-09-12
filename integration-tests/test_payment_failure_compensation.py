import asyncio
import time

import pytest

from helpers import INVENTORY_SERVICE_URL, ORDER_SERVICE_URL, wait_for_order_terminal


async def _wait_for_stock_restored(client, sku: str, expected_qty: int, timeout: float = 10.0):
    """inventory-service restores stock by independently consuming
    payment.failed, in parallel with order-service marking the order
    FAILED -- so it can lag slightly behind the order reaching terminal
    status."""
    deadline = time.monotonic() + timeout
    qty = None
    while time.monotonic() < deadline:
        resp = await client.get(f"{INVENTORY_SERVICE_URL}/admin/stock")
        resp.raise_for_status()
        qty = next(s["available_qty"] for s in resp.json() if s["sku"] == sku)
        if qty == expected_qty:
            return
        await asyncio.sleep(0.5)
    raise TimeoutError(f"{sku} stock never restored to {expected_qty}, last seen {qty}")


@pytest.mark.asyncio
async def test_payment_failure_triggers_compensation_and_restores_stock(client):
    stock_before_resp = await client.get(f"{INVENTORY_SERVICE_URL}/admin/stock")
    stock_before_resp.raise_for_status()
    before = {s["sku"]: s["available_qty"] for s in stock_before_resp.json()}

    resp = await client.post(
        f"{ORDER_SERVICE_URL}/orders",
        json={
            "customer_id": "cust-1",
            "items": [{"sku": "SKU-1", "qty": 3}],
            "amount_cents": 2000,
            "force_payment_failure": True,
        },
    )
    assert resp.status_code == 201
    order = resp.json()

    final = await wait_for_order_terminal(client, order["order_id"])

    assert final["status"] == "FAILED"
    assert final["failure_reason"] == "PAYMENT_DECLINED"
    statuses = [h["status"] for h in final["history"]]
    assert statuses[:3] == ["PENDING", "INVENTORY_RESERVED", "FAILED"]

    await _wait_for_stock_restored(client, "SKU-1", before["SKU-1"])
