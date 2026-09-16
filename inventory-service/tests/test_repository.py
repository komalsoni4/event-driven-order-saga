import asyncio

import pytest

from app.repository import (
    ReservationRepository,
    StockRepository,
    consume_chaos_attempt,
)
from app.seed import SEED_STOCK


@pytest.fixture
async def stock_repo(db):
    repo = StockRepository(db)
    await repo.seed_if_empty(SEED_STOCK)
    return repo


@pytest.fixture
async def reservation_repo(db):
    repo = ReservationRepository(db)
    await repo.ensure_indexes()
    return repo


@pytest.mark.asyncio
async def test_reserve_items_succeeds_when_stock_available(stock_repo):
    success, unavailable = await stock_repo.reserve_items([{"sku": "SKU-1", "qty": 5}])
    assert success is True
    assert unavailable == []

    stock = {doc["_id"]: doc for doc in await stock_repo.list_stock()}
    assert stock["SKU-1"]["available_qty"] == 95
    assert stock["SKU-1"]["reserved_qty"] == 5


@pytest.mark.asyncio
async def test_reserve_items_fails_and_reports_unavailable_sku(stock_repo):
    # SKU-5 is seeded with only 2 units available.
    success, unavailable = await stock_repo.reserve_items([{"sku": "SKU-5", "qty": 5}])
    assert success is False
    assert unavailable == ["SKU-5"]


@pytest.mark.asyncio
async def test_reserve_items_rolls_back_earlier_items_on_partial_failure(stock_repo):
    # SKU-1 has plenty of stock, SKU-5 doesn't - the whole multi-item
    # reservation must fail atomically, with SKU-1's partial reservation
    # rolled back rather than left dangling.
    success, unavailable = await stock_repo.reserve_items(
        [{"sku": "SKU-1", "qty": 10}, {"sku": "SKU-5", "qty": 5}]
    )
    assert success is False
    assert unavailable == ["SKU-5"]

    stock = {doc["_id"]: doc for doc in await stock_repo.list_stock()}
    assert stock["SKU-1"]["available_qty"] == 100
    assert stock["SKU-1"]["reserved_qty"] == 0


@pytest.mark.asyncio
async def test_release_items_restores_availability(stock_repo):
    await stock_repo.reserve_items([{"sku": "SKU-1", "qty": 5}])
    await stock_repo.release_items([{"sku": "SKU-1", "qty": 5}])

    stock = {doc["_id"]: doc for doc in await stock_repo.list_stock()}
    assert stock["SKU-1"]["available_qty"] == 100
    assert stock["SKU-1"]["reserved_qty"] == 0


@pytest.mark.asyncio
async def test_concurrent_reservations_never_oversell_stock(stock_repo):
    attempts = await asyncio.gather(
        *[
            stock_repo.reserve_items([{"sku": "SKU-5", "qty": 1}])
            for _ in range(10)
        ]
    )

    successful_reservations = [success for success, _ in attempts if success]
    stock = {doc["_id"]: doc for doc in await stock_repo.list_stock()}

    assert len(successful_reservations) == 2
    assert stock["SKU-5"]["available_qty"] == 0
    assert stock["SKU-5"]["reserved_qty"] == 2


@pytest.mark.asyncio
async def test_reservation_create_and_lookup_by_order_id(reservation_repo):
    doc = await reservation_repo.create("order-1", [{"sku": "SKU-1", "qty": 1}])
    found = await reservation_repo.get_by_order_id("order-1")
    assert found["_id"] == doc["_id"]
    assert found["status"] == "RESERVED"


@pytest.mark.asyncio
async def test_reservation_order_id_is_unique(reservation_repo):
    await reservation_repo.create("order-1", [{"sku": "SKU-1", "qty": 1}])
    with pytest.raises(Exception):
        await reservation_repo.create("order-1", [{"sku": "SKU-1", "qty": 1}])


@pytest.mark.asyncio
async def test_reservation_mark_released(reservation_repo):
    doc = await reservation_repo.create("order-1", [{"sku": "SKU-1", "qty": 1}])
    await reservation_repo.mark_released(doc["_id"])
    found = await reservation_repo.get_by_order_id("order-1")
    assert found["status"] == "RELEASED"


@pytest.mark.asyncio
async def test_chaos_attempt_fails_for_configured_number_of_tries_then_succeeds(db):
    # limit=2 means the first two attempts should still fail, the third
    # should be let through.
    assert await consume_chaos_attempt(db, "evt-1", limit=2) is True
    assert await consume_chaos_attempt(db, "evt-1", limit=2) is True
    assert await consume_chaos_attempt(db, "evt-1", limit=2) is False


@pytest.mark.asyncio
async def test_chaos_attempt_disabled_when_limit_is_zero(db):
    assert await consume_chaos_attempt(db, "evt-1", limit=0) is False
