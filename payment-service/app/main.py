import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
from .consumers import PaymentConsumerHandlers, build_consumers
from .publisher import PaymentEventPublisher
from .repository import PaymentRepository

configure_logging()
logger = logging.getLogger("payment-service")

settings = SagaSettings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    mongo_client = get_client(settings.mongo_url)
    db = get_database(mongo_client, "payments_db")

    payment_repo = PaymentRepository(db)
    await payment_repo.ensure_indexes()
    await ensure_idempotency_indexes(db)

    connection = await connect(settings.rabbitmq_url)
    publish_channel = await connection.channel()
    consume_channel = await connection.channel()

    publisher = PaymentEventPublisher(Publisher(publish_channel))

    app.state.payment_repo = payment_repo

    handlers = PaymentConsumerHandlers(
        db, payment_repo, publisher, settings.payment_fail_threshold_cents
    )
    consumers = build_consumers(
        consume_channel, handlers, settings.max_retries, settings.retry_base_delay_ms
    )
    for consumer in consumers:
        await consumer.start()
    logger.info("payment-service started with %d consumers", len(consumers))

    yield

    await connection.close()
    mongo_client.close()


app = FastAPI(title="payment-service", lifespan=lifespan)
app.state.admin_api_key = settings.admin_api_key
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Admin-API-Key", "X-Correlation-ID"],
)
app.add_middleware(CorrelationIdMiddleware)
app.add_middleware(MetricsMiddleware, service_name="payment-service")
app.include_router(router)
app.add_api_route("/metrics", metrics_response, methods=["GET"])
