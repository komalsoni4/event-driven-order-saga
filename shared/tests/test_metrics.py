from fastapi import FastAPI
from fastapi.testclient import TestClient
from prometheus_client import generate_latest

from saga_shared.observability import MetricsMiddleware


def test_metrics_middleware_records_http_requests():
    app = FastAPI()
    app.add_middleware(MetricsMiddleware, service_name="test-service")

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    metrics = generate_latest().decode()
    assert 'saga_http_requests_total{method="GET",route="/health",service="test-service",status="200"}' in metrics
