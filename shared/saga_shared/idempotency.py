"""Generic event-dedup layer used by every consumer.

RabbitMQ gives at-least-once delivery (a message can be redelivered after a
requeue, a crash before ack, etc). Every service records the ``event_id`` of
each event it has already handled in a ``processed_events`` collection before
doing any business-logic writes, so a redelivered event is a safe no-op
instead of a double-charge / double-reservation.

This collection is deliberately NOT written atomically with the business
write + outgoing publish that follow it (that would require a Mongo
transaction plus a transactional-outbox relay process). That gap is a known,
documented trade-off - see the README "Trade-offs" section.
"""
from __future__ import annotations

from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError

PROCESSED_EVENTS_COLLECTION = "processed_events"
TTL_SECONDS = 30 * 24 * 3600  # 30 days


async def ensure_idempotency_indexes(db: AsyncIOMotorDatabase) -> None:
    await db[PROCESSED_EVENTS_COLLECTION].create_index(
        "processed_at", expireAfterSeconds=TTL_SECONDS
    )


async def try_mark_processed(db: AsyncIOMotorDatabase, event_id: str, event_type: str) -> bool:
    """Record that we're about to process ``event_id``.

    Returns True the first time (caller should proceed), False if this
    event_id was already recorded (caller should ack and skip - it's a
    redelivery of an event we already handled).
    """
    try:
        await db[PROCESSED_EVENTS_COLLECTION].insert_one(
            {
                "_id": event_id,
                "event_type": event_type,
                "processed_at": datetime.now(timezone.utc),
            }
        )
        return True
    except DuplicateKeyError:
        return False
