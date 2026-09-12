import asyncio
import os
import time

import httpx

ORDER_SERVICE_URL = os.environ.get("ORDER_SERVICE_URL", "http://localhost:8001")
INVENTORY_SERVICE_URL = os.environ.get("INVENTORY_SERVICE_URL", "http://localhost:8002")
PAYMENT_SERVICE_URL = os.environ.get("PAYMENT_SERVICE_URL", "http://localhost:8003")

TERMINAL_STATUSES = {"CONFIRMED", "FAILED"}


async def wait_for_order_terminal(client: httpx.AsyncClient, order_id: str, timeout: float = 15.0) -> dict:
    deadline = time.monotonic() + timeout
    order = None
    while time.monotonic() < deadline:
        resp = await client.get(f"{ORDER_SERVICE_URL}/orders/{order_id}")
        resp.raise_for_status()
        order = resp.json()
        if order["status"] in TERMINAL_STATUSES:
            return order
        await asyncio.sleep(0.5)
    raise TimeoutError(f"order {order_id} did not reach a terminal status within {timeout}s, last seen: {order}")
