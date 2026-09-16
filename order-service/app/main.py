import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from saga_shared.config import SagaSettings
from saga_shared.idempotency import ensure_idempotency_indexes
from saga_shared.mongo import get_client, get_database
from saga_shared.observability import (
    CorrelationIdMiddleware,
    MetricsMiddleware,
    configure_logging,
    metrics_response,
)
from saga_shared.rabbitmq import Publisher, connect

from .api import router
from .consumers import OrderConsumerHandlers, build_consumers
from .publisher import OrderEventPublisher
from .repository import OrderRepository

configure_logging()
logger = logging.getLogger("order-service")

settings = SagaSettings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    mongo_client = get_client(settings.mongo_url)
    db = get_database(mongo_client, "orders_db")
    repo = OrderRepository(db)
    await repo.ensure_indexes()
    await ensure_idempotency_indexes(db)

    connection = await connect(settings.rabbitmq_url)
    publish_channel = await connection.channel()
    consume_channel = await connection.channel()

    app.state.repo = repo
    app.state.publisher = OrderEventPublisher(Publisher(publish_channel))

    handlers = OrderConsumerHandlers(db, repo)
    consumers = build_consumers(
        consume_channel, handlers, settings.max_retries, settings.retry_base_delay_ms
    )
    for consumer in consumers:
        await consumer.start()
    logger.info("order-service started with %d consumers", len(consumers))

    yield

    await connection.close()
    mongo_client.close()


app = FastAPI(title="order-service", lifespan=lifespan)
app.add_middleware(CorrelationIdMiddleware)
app.add_middleware(MetricsMiddleware, service_name="order-service")
app.include_router(router)
app.add_api_route("/metrics", metrics_response, methods=["GET"])
