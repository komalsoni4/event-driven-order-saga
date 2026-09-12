from __future__ import annotations

import uuid
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase

from .models import FailureReason, OrderStatus

ORDERS_COLLECTION = "orders"
TERMINAL_STATUSES = {OrderStatus.CONFIRMED.value, OrderStatus.FAILED.value}


def new_order_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class OrderRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self._db = db

    async def ensure_indexes(self) -> None:
        await self._db[ORDERS_COLLECTION].create_index("status")
        await self._db[ORDERS_COLLECTION].create_index("created_at")

    async def create_order(
        self,
        customer_id: str,
        items: list[dict],
        amount_cents: int,
        force_payment_failure: bool,
        simulate_transient_failure_count: int,
    ) -> dict:
        order_id = new_order_id()
        now = utcnow()
        doc = {
            "_id": order_id,
            "customer_id": customer_id,
            "items": items,
            "amount_cents": amount_cents,
            "status": OrderStatus.PENDING.value,
            "failure_reason": None,
            "force_payment_failure": force_payment_failure,
            "simulate_transient_failure_count": simulate_transient_failure_count,
            "history": [{"status": OrderStatus.PENDING.value, "at": now}],
            "created_at": now,
            "updated_at": now,
        }
        await self._db[ORDERS_COLLECTION].insert_one(doc)
        return doc

    async def get_order(self, order_id: str) -> dict | None:
        return await self._db[ORDERS_COLLECTION].find_one({"_id": order_id})

    async def list_orders(self, limit: int = 50) -> list[dict]:
        cursor = self._db[ORDERS_COLLECTION].find().sort("created_at", -1).limit(limit)
        return [doc async for doc in cursor]

    async def transition_status(
        self,
        order_id: str,
        status: OrderStatus,
        failure_reason: FailureReason | None = None,
    ) -> bool:
        """Move an order to ``status``, unless it's already in a terminal
        state (CONFIRMED/FAILED) - guards against events arriving out of
        order in a choreography saga (e.g. a stale retry landing after the
        order was already finalized by a different event).

        Returns True if the transition was applied, False if it was ignored
        because the order was already terminal.
        """
        now = utcnow()
        set_fields: dict = {"status": status.value, "updated_at": now}
        if failure_reason is not None:
            set_fields["failure_reason"] = failure_reason.value
        result = await self._db[ORDERS_COLLECTION].update_one(
            {"_id": order_id, "status": {"$nin": list(TERMINAL_STATUSES)}},
            {
                "$set": set_fields,
                "$push": {"history": {"status": status.value, "at": now}},
            },
        )
        return result.modified_count == 1

    async def append_audit(self, order_id: str, note: str) -> None:
        await self._db[ORDERS_COLLECTION].update_one(
            {"_id": order_id},
            {"$push": {"history": {"status": note, "at": utcnow()}}},
        )
