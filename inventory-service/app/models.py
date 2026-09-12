from enum import StrEnum

from pydantic import BaseModel


class ReservationStatus(StrEnum):
    RESERVED = "RESERVED"
    RELEASED = "RELEASED"


class StockView(BaseModel):
    sku: str
    available_qty: int
    reserved_qty: int


class ReservationView(BaseModel):
    reservation_id: str
    order_id: str
    items: list[dict]
    status: ReservationStatus
