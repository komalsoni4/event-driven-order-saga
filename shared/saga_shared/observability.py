import json
import logging
import time
import uuid
from contextvars import ContextVar

from prometheus_client import Counter, Histogram, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)

HTTP_REQUESTS = Counter(
    "saga_http_requests_total",
    "Total HTTP requests handled by saga services.",
    ("service", "method", "route", "status"),
)
HTTP_REQUEST_DURATION = Histogram(
    "saga_http_request_duration_seconds",
    "HTTP request duration in seconds.",
    ("service", "method", "route"),
)
EVENTS_PUBLISHED = Counter(
    "saga_events_published_total",
    "Total saga events published to RabbitMQ.",
    ("event_type",),
)
EVENTS_CONSUMED = Counter(
    "saga_events_consumed_total",
    "Total saga events successfully handled.",
    ("queue", "event_type"),
)
EVENT_HANDLER_FAILURES = Counter(
    "saga_event_handler_failures_total",
    "Total saga event handler failures.",
    ("queue",),
)
EVENT_RETRIES = Counter(
    "saga_event_retries_total",
    "Total saga event retries scheduled.",
    ("queue",),
)
EVENTS_PARKED = Counter(
    "saga_events_parked_total",
    "Total saga events moved to parked queues.",
    ("queue",),
)


def get_correlation_id() -> str | None:
    return _correlation_id.get()


def set_correlation_id(value: str):
    return _correlation_id.set(value)


def reset_correlation_id(token) -> None:
    _correlation_id.reset(token)


def metrics_response() -> Response:
    return Response(generate_latest(), media_type="text/plain; version=0.0.4")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        correlation_id = get_correlation_id()
        if correlation_id:
            entry["correlation_id"] = correlation_id
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry)


class MetricsMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, service_name: str):
        super().__init__(app)
        self.service_name = service_name

    async def dispatch(self, request: Request, call_next):
        started = time.perf_counter()
        response = await call_next(request)
        route = request.scope.get("route")
        route_path = getattr(route, "path", request.url.path)
        labels = {
            "service": self.service_name,
            "method": request.method,
            "route": route_path,
        }
        HTTP_REQUESTS.labels(**labels, status=str(response.status_code)).inc()
        HTTP_REQUEST_DURATION.labels(**labels).observe(time.perf_counter() - started)
        return response


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
        token = set_correlation_id(correlation_id)
        try:
            response = await call_next(request)
            response.headers["X-Correlation-ID"] = correlation_id
            return response
        finally:
            reset_correlation_id(token)
