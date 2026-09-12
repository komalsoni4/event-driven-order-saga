from __future__ import annotations

import uuid
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase

PAYMENTS_COLLECTION = "payments"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PaymentRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self._db = db

    async def ensure_indexes(self) -> None:
        await self._db[PAYMENTS_COLLECTION].create_index("order_id")

    async def create(
        self, order_id: str, amount_cents: int, status: str, reason: str | None = None
    ) -> dict:
        payment_id = str(uuid.uuid4())
        doc = {
            "_id": payment_id,
            "order_id": order_id,
            "amount_cents": amount_cents,
            "status": status,
            "reason": reason,
            "created_at": utcnow(),
        }
        await self._db[PAYMENTS_COLLECTION].insert_one(doc)
        return doc

    async def list_payments(self, limit: int = 50) -> list[dict]:
        cursor = self._db[PAYMENTS_COLLECTION].find().sort("created_at", -1).limit(limit)
        return [doc async for doc in cursor]
