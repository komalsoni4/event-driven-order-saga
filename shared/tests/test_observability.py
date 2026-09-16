import json
import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient

from saga_shared.events import EventEnvelope, EventType, InventoryReleasedPayload
from saga_shared.observability import (
    CorrelationIdMiddleware,
    JsonFormatter,
    reset_correlation_id,
    set_correlation_id,
)


def test_event_envelope_keeps_active_correlation_id():
    token = set_correlation_id("trace-123")
    try:
        envelope = EventEnvelope.create(
            EventType.INVENTORY_RELEASED,
            InventoryReleasedPayload(order_id="order-1", reservation_id="reservation-1"),
        )
        assert envelope.correlation_id == "trace-123"
    finally:
        reset_correlation_id(token)


def test_http_middleware_returns_correlation_id():
    app = FastAPI()
    app.add_middleware(CorrelationIdMiddleware)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    with TestClient(app) as client:
        response = client.get("/health", headers={"X-Correlation-ID": "trace-456"})

    assert response.status_code == 200
    assert response.headers["X-Correlation-ID"] == "trace-456"


def test_json_formatter_includes_correlation_id():
    token = set_correlation_id("trace-789")
    try:
        record = logging.LogRecord(
            "test", logging.INFO, __file__, 1, "order accepted", (), None
        )
        output = json.loads(JsonFormatter().format(record))
    finally:
        reset_correlation_id(token)

    assert output["message"] == "order accepted"
    assert output["correlation_id"] == "trace-789"
