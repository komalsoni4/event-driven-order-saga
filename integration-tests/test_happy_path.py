import pytest

from helpers import ORDER_SERVICE_URL, wait_for_order_terminal


@pytest.mark.asyncio
async def test_happy_path_confirms_order(client):
    resp = await client.post(
        f"{ORDER_SERVICE_URL}/orders",
        json={
            "customer_id": "cust-1",
            "items": [{"sku": "SKU-1", "qty": 2}],
            "amount_cents": 5000,
        },
    )
    assert resp.status_code == 201
    order = resp.json()

    final = await wait_for_order_terminal(client, order["order_id"])

    assert final["status"] == "CONFIRMED"
    statuses = [h["status"] for h in final["history"]]
    assert statuses == ["PENDING", "INVENTORY_RESERVED", "CONFIRMED"]
