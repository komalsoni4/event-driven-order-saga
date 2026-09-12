import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from saga_shared.config import SagaSettings
from saga_shared.idempotency import ensure_idempotency_indexes
from saga_shared.mongo import get_client, get_database
from saga_shared.rabbitmq import Publisher, connect

from .api import router
from .consumers import InventoryConsumerHandlers, build_consumers
from .publisher import InventoryEventPublisher
from .repository import ReservationRepository, StockRepository
from .seed import SEED_STOCK

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("inventory-service")

settings = SagaSettings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    mongo_client = get_client(settings.mongo_url)
    db = get_database(mongo_client, "inventory_db")

    stock_repo = StockRepository(db)
    reservation_repo = ReservationRepository(db)
    await stock_repo.ensure_indexes()
    await reservation_repo.ensure_indexes()
    await ensure_idempotency_indexes(db)
    await stock_repo.seed_if_empty(SEED_STOCK)

    connection = await connect(settings.rabbitmq_url)
    publish_channel = await connection.channel()
    consume_channel = await connection.channel()

    publisher = InventoryEventPublisher(Publisher(publish_channel))

    app.state.db = db
    app.state.stock_repo = stock_repo
    app.state.reservation_repo = reservation_repo

    handlers = InventoryConsumerHandlers(db, stock_repo, reservation_repo, publisher)
    consumers = build_consumers(
        consume_channel, handlers, settings.max_retries, settings.retry_base_delay_ms
    )
    for consumer in consumers:
        await consumer.start()
    logger.info("inventory-service started with %d consumers", len(consumers))

    yield

    await connection.close()
    mongo_client.close()


app = FastAPI(title="inventory-service", lifespan=lifespan)
app.include_router(router)
