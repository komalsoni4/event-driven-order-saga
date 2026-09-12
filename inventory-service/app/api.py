from fastapi import APIRouter, Request

from .models import StockView
from .repository import StockRepository
from .seed import SEED_STOCK

router = APIRouter()


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/admin/stock", response_model=list[StockView])
async def list_stock(req: Request):
    repo: StockRepository = req.app.state.stock_repo
    docs = await repo.list_stock()
    return [
        StockView(sku=doc["_id"], available_qty=doc["available_qty"], reserved_qty=doc["reserved_qty"])
        for doc in docs
    ]


@router.post("/admin/reset-stock", response_model=list[StockView])
async def reset_stock(req: Request):
    """Wipes and re-seeds stock so a live demo can be repeated without
    restarting containers."""
    repo: StockRepository = req.app.state.stock_repo
    await req.app.state.db.drop_collection("stock")
    await repo.seed_if_empty(SEED_STOCK)
    docs = await repo.list_stock()
    return [
        StockView(sku=doc["_id"], available_qty=doc["available_qty"], reserved_qty=doc["reserved_qty"])
        for doc in docs
    ]
