import pytest
from mongomock_motor import AsyncMongoMockClient

from saga_shared.idempotency import ensure_idempotency_indexes, try_mark_processed


@pytest.fixture
def db():
    client = AsyncMongoMockClient()
    return client["test_db"]


@pytest.mark.asyncio
async def test_first_time_event_is_processed(db):
    await ensure_idempotency_indexes(db)
    assert await try_mark_processed(db, "evt-1", "order.created") is True


@pytest.mark.asyncio
async def test_duplicate_event_is_skipped(db):
    await ensure_idempotency_indexes(db)
    assert await try_mark_processed(db, "evt-1", "order.created") is True
    assert await try_mark_processed(db, "evt-1", "order.created") is False


@pytest.mark.asyncio
async def test_different_events_both_processed(db):
    await ensure_idempotency_indexes(db)
    assert await try_mark_processed(db, "evt-1", "order.created") is True
    assert await try_mark_processed(db, "evt-2", "order.created") is True
