import pytest

from helpers import ORDER_SERVICE_URL, wait_for_order_terminal


@pytest.mark.asyncio
async def test_insufficient_stock_short_circuits_before_payment(client):
    # SKU-5 is seeded with only 2 units available (see inventory-service/app/seed.py).
    resp = await client.post(
        f"{ORDER_SERVICE_URL}/orders",
        json={
            "customer_id": "cust-1",
            "items": [{"sku": "SKU-5", "qty": 10}],
            "amount_cents": 1000,
        },
    )
    assert resp.status_code == 201
    order = resp.json()

    final = await wait_for_order_terminal(client, order["order_id"])

    assert final["status"] == "FAILED"
    assert final["failure_reason"] == "INSUFFICIENT_STOCK"
    statuses = [h["status"] for h in final["history"]]
    assert statuses == ["PENDING", "FAILED"]
