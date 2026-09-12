from fastapi import APIRouter, HTTPException, Request

from saga_shared.events import OrderCreatedPayload

from .models import CreateOrderRequest, OrderResponse
from .publisher import OrderEventPublisher
from .repository import OrderRepository

router = APIRouter()


def _to_response(doc: dict) -> OrderResponse:
    return OrderResponse(
        order_id=doc["_id"],
        customer_id=doc["customer_id"],
        items=doc["items"],
        amount_cents=doc["amount_cents"],
        status=doc["status"],
        failure_reason=doc.get("failure_reason"),
        history=doc["history"],
        created_at=doc["created_at"],
        updated_at=doc["updated_at"],
    )


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.post("/orders", response_model=OrderResponse, status_code=201)
async def create_order(request: CreateOrderRequest, req: Request):
    repo: OrderRepository = req.app.state.repo
    publisher: OrderEventPublisher = req.app.state.publisher

    doc = await repo.create_order(
        customer_id=request.customer_id,
        items=[item.model_dump() for item in request.items],
        amount_cents=request.amount_cents,
        force_payment_failure=request.force_payment_failure,
        simulate_transient_failure_count=request.simulate_transient_failure_count,
    )
    await publisher.order_created(
        OrderCreatedPayload(
            order_id=doc["_id"],
            customer_id=doc["customer_id"],
            items=request.items,
            amount_cents=doc["amount_cents"],
            force_payment_failure=doc["force_payment_failure"],
            simulate_transient_failure_count=doc["simulate_transient_failure_count"],
        )
    )
    return _to_response(doc)


@router.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(order_id: str, req: Request):
    repo: OrderRepository = req.app.state.repo
    doc = await repo.get_order(order_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="order not found")
    return _to_response(doc)


@router.get("/admin/orders", response_model=list[OrderResponse])
async def list_orders(req: Request, limit: int = 50):
    repo: OrderRepository = req.app.state.repo
    docs = await repo.list_orders(limit)
    return [_to_response(doc) for doc in docs]
