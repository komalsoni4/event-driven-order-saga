from fastapi import APIRouter, Depends, Request

from saga_shared.auth import require_admin_api_key

router = APIRouter()


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/admin/payments", dependencies=[Depends(require_admin_api_key)])
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
