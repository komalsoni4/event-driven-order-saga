from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/admin/payments")
async def list_payments(req: Request, limit: int = 50):
    repo = req.app.state.payment_repo
    docs = await repo.list_payments(limit)
    return [
        {
            "payment_id": doc["_id"],
            "order_id": doc["order_id"],
            "amount_cents": doc["amount_cents"],
            "status": doc["status"],
            "reason": doc.get("reason"),
        }
        for doc in docs
    ]
