import asyncio
import time

import httpx
import pytest

from helpers import INVENTORY_SERVICE_URL, ORDER_SERVICE_URL, PAYMENT_SERVICE_URL

SERVICE_URLS = (ORDER_SERVICE_URL, INVENTORY_SERVICE_URL, PAYMENT_SERVICE_URL)
ADMIN_HEADERS = {"X-Admin-API-Key": "local-admin-key"}


@pytest.fixture(scope="session", autouse=True)
async def wait_for_services():
    async with httpx.AsyncClient(timeout=5) as client:
        for url in SERVICE_URLS:
            deadline = time.monotonic() + 60
            while True:
                try:
                    resp = await client.get(f"{url}/health")
                    if resp.status_code == 200:
                        break
                except httpx.RequestError:
                    pass
                if time.monotonic() > deadline:
                    raise RuntimeError(f"{url} never became healthy within 60s")
                await asyncio.sleep(1)


@pytest.fixture
async def client():
    async with httpx.AsyncClient(timeout=10) as c:
        yield c


@pytest.fixture(autouse=True)
async def reset_stock(client):
    resp = await client.post(
        f"{INVENTORY_SERVICE_URL}/admin/reset-stock", headers=ADMIN_HEADERS
    )
    resp.raise_for_status()
