from __future__ import annotations

import uuid
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument

from .models import ReservationStatus

STOCK_COLLECTION = "stock"
RESERVATIONS_COLLECTION = "reservations"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class StockRepository:
    """Owns the `stock` collection. Reservation is a two-step, rollback-aware
    operation across possibly multiple SKUs: each item is reserved with an
    atomic guarded update (`available_qty >= qty`), and if any item in the
    order can't be reserved, whatever was already reserved for earlier items
    in the same order is rolled back so a partially-reservable order never
    holds partial stock.
    """

    def __init__(self, db: AsyncIOMotorDatabase):
        self._db = db

    async def ensure_indexes(self) -> None:
        pass  # `_id` is already unique/indexed by Mongo.

    async def seed_if_empty(self, seed: list[dict]) -> None:
        if await self._db[STOCK_COLLECTION].count_documents({}) > 0:
            return
        now = utcnow()
        docs = [
            {
                "_id": item["sku"],
                "available_qty": item["available_qty"],
                "reserved_qty": 0,
                "updated_at": now,
            }
            for item in seed
        ]
        await self._db[STOCK_COLLECTION].insert_many(docs)

    async def list_stock(self) -> list[dict]:
        return [doc async for doc in self._db[STOCK_COLLECTION].find()]

    async def reserve_items(self, items: list[dict]) -> tuple[bool, list[str]]:
        reserved: list[dict] = []
        unavailable: list[str] = []
        for item in items:
            sku, qty = item["sku"], item["qty"]
            result = await self._db[STOCK_COLLECTION].find_one_and_update(
                {"_id": sku, "available_qty": {"$gte": qty}},
                {"$inc": {"available_qty": -qty, "reserved_qty": qty}, "$set": {"updated_at": utcnow()}},
            )
            if result is None:
                unavailable.append(sku)
                break
            reserved.append(item)

        if unavailable:
            for item in reserved:
                await self._db[STOCK_COLLECTION].update_one(
                    {"_id": item["sku"]},
                    {"$inc": {"available_qty": item["qty"], "reserved_qty": -item["qty"]}},
                )
            return False, unavailable
        return True, []

    async def release_items(self, items: list[dict]) -> None:
        for item in items:
            await self._db[STOCK_COLLECTION].update_one(
                {"_id": item["sku"]},
                {
                    "$inc": {"available_qty": item["qty"], "reserved_qty": -item["qty"]},
                    "$set": {"updated_at": utcnow()},
                },
            )


class ReservationRepository:
    """Owns the `reservations` collection. The unique index on `order_id` is
    a defense-in-depth guard against double-reservation, independent of the
    generic event-level idempotency check.
    """

    def __init__(self, db: AsyncIOMotorDatabase):
        self._db = db

    async def ensure_indexes(self) -> None:
        await self._db[RESERVATIONS_COLLECTION].create_index("order_id", unique=True)

    async def create(self, order_id: str, items: list[dict]) -> dict:
        reservation_id = str(uuid.uuid4())
        now = utcnow()
        doc = {
            "_id": reservation_id,
            "order_id": order_id,
            "items": items,
            "status": ReservationStatus.RESERVED.value,
            "created_at": now,
            "updated_at": now,
        }
        await self._db[RESERVATIONS_COLLECTION].insert_one(doc)
        return doc

    async def get_by_order_id(self, order_id: str) -> dict | None:
        return await self._db[RESERVATIONS_COLLECTION].find_one({"order_id": order_id})

    async def mark_released(self, reservation_id: str) -> None:
        await self._db[RESERVATIONS_COLLECTION].update_one(
            {"_id": reservation_id},
            {"$set": {"status": ReservationStatus.RELEASED.value, "updated_at": utcnow()}},
        )


CHAOS_COLLECTION = "chaos_attempts"


async def consume_chaos_attempt(db: AsyncIOMotorDatabase, event_id: str, limit: int) -> bool:
    """Demo-only failure injection: returns True while the caller should
    still raise a simulated transient failure for this event_id (i.e. the
    number of attempts so far is <= limit), False once it should let the
    event through. Lets `order.created`'s `simulate_transient_failure_count`
    field trigger the retry/backoff path on demand for a live demo.
    """
    if limit <= 0:
        return False
    doc = await db[CHAOS_COLLECTION].find_one_and_update(
        {"_id": event_id},
        {"$inc": {"attempts": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return doc["attempts"] <= limit
