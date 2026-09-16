# Event-Driven Order Saga: Project Guide

This document explains the project from beginner concepts to implementation details. It is intended for learning, interviews, onboarding, and future deployment work.

## 1. Project Purpose

This project models an online order workflow using independent microservices.

An order is not completed in one database transaction. It crosses several services:

1. The order service receives the order.
2. The inventory service checks and reserves stock.
3. The payment service approves or declines payment.
4. The order service confirms or fails the order.
5. If payment fails after stock was reserved, inventory releases the stock.

The project demonstrates how a distributed system remains consistent when a later step fails after an earlier step has already succeeded.

The main learning goals are:

- Microservice communication
- Asynchronous event-driven design
- RabbitMQ messaging
- MongoDB persistence
- Saga transactions and compensation
- Retries and dead-letter queues
- Idempotent event processing
- Docker-based local development
- CI/CD with GitHub Actions
- Observability with logs, correlation IDs, and Prometheus metrics
- Concurrency-safe inventory reservations
- Protected administrative APIs
- A dashboard for understanding the workflow

## 2. Business Example

Imagine a customer buys two products.

A simple monolith might execute all steps inside one application. This project separates the responsibilities:

```text
Customer
   |
   v
Order Service
   |
   | order.created
   v
Inventory Service
   |
   | inventory.reserved
   v
Payment Service
   |
   | payment.completed
   v
Order becomes CONFIRMED
```

The services communicate through events rather than direct service-to-service business calls.

## 3. Architecture

### Services

#### Order service

Location: `order-service/`

Responsibilities:

- Accept `POST /orders` requests
- Store order records
- Track order status and history
- Publish `order.created`
- Consume inventory and payment events
- Mark orders as confirmed or failed

Port: `8001`

#### Inventory service

Location: `inventory-service/`

Responsibilities:

- Own product stock
- Reserve available stock
- Release stock during compensation
- Publish inventory events
- Seed a demo catalog at startup
- Provide protected stock administration endpoints

Port: `8002`

#### Payment service

Location: `payment-service/`

Responsibilities:

- Consume inventory-reserved events
- Create payment records
- Approve or decline payment deterministically
- Publish payment events

Port: `8003`

#### Web UI

Location: `web-ui/`

Responsibilities:

- Show service health
- Create demo orders
- Show inventory levels
- Show recent orders and their journey
- Show payment results
- Show metrics-oriented operational information
- Provide guided success, payment-failure, and stock-failure scenarios

Port: `8080`

### Infrastructure

#### MongoDB

MongoDB stores documents for each service. Each service owns its own logical database:

- `orders_db`
- `inventory_db`
- `payments_db`

Port: `27017`

#### RabbitMQ

RabbitMQ is the event broker. It receives events from publishers and routes them to consumer queues.

Ports:

- AMQP: `5672`
- Management UI: `15672`

RabbitMQ management UI credentials for local development are normally `guest` / `guest`.

## 4. Technology Definitions

### Python

The programming language used by all backend services. The project targets Python 3.11.

### FastAPI

A Python web framework used to build REST APIs. It provides request validation, routing, OpenAPI documentation, and asynchronous endpoint support.

### Uvicorn

The ASGI server that runs each FastAPI application.

### Pydantic

Used to validate request bodies, event payloads, and response models. It prevents malformed data from silently entering the workflow.

### MongoDB

A document database. It is suitable for this project because orders, inventory records, payments, and history are naturally represented as documents.

### Motor

The asynchronous MongoDB driver used by the Python services.

### RabbitMQ

A message broker. Producers publish events and consumers receive events from queues.

### AMQP

The messaging protocol used by RabbitMQ. This project uses AMQP through `aio-pika`.

### aio-pika

The asynchronous Python RabbitMQ client used to connect, publish messages, consume messages, acknowledge messages, and configure queues.

### Docker

Packages each service with its runtime and dependencies so it behaves consistently across machines.

### Docker Compose

Starts the full local system with one command, including the application services, MongoDB, RabbitMQ, and the dashboard.

### Nginx

Serves the static dashboard files from the `web-ui` container.

### GitHub Actions

Runs automated tests and Docker integration checks on pushes and pull requests.

### Prometheus metrics

The services expose `/metrics` endpoints containing counters and histograms for requests, events, failures, retries, and parked messages.

## 5. Event-Driven Design

An event is a record that says something already happened.

Examples:

- `order.created`
- `inventory.reserved`
- `inventory.reservation_failed`
- `payment.completed`
- `payment.failed`
- `inventory.released`

An event envelope contains:

- `event_id`: unique event identifier
- `correlation_id`: trace identifier shared across the workflow
- `event_type`: event name
- `occurred_at`: creation time
- `payload`: business data

The `correlation_id` allows the same order workflow to be followed across all services and logs.

## 6. Saga Pattern

A Saga is a distributed business transaction made from multiple local transactions.

A traditional database transaction can roll back all changes when something fails. That is not directly possible when each microservice owns a separate database.

A Saga uses compensating actions instead.

Example:

```text
Reserve stock
   |
   | payment fails
   v
Release stock
```

This project uses choreography. There is no central saga coordinator. Each service listens to events and decides what to do next.

### Why choreography is used here

There are only three business services, so a coordinator would add another service and another communication hop. Each service has a clear reaction to the events it receives.

For a much larger workflow with many branches, an orchestrator such as Temporal or a dedicated state machine might be easier to manage.

## 7. Complete Happy-Path Flow

A successful order follows these steps:

1. A client sends `POST /orders` to the order service.
2. The order service stores the order as `PENDING`.
3. The order service publishes `order.created`.
4. Inventory consumes the event.
5. Inventory atomically decreases available stock and increases reserved stock.
6. Inventory publishes `inventory.reserved`.
7. Payment consumes `inventory.reserved`.
8. Payment creates a successful payment record.
9. Payment publishes `payment.completed`.
10. Order service consumes `payment.completed`.
11. The order becomes `CONFIRMED`.

The visible status history is:

```text
PENDING -> INVENTORY_RESERVED -> CONFIRMED
```

## 8. Failure Conditions and Handling

### Failure: insufficient stock

Flow:

```text
order.created
   -> inventory cannot reserve requested quantity
   -> inventory.reservation_failed
   -> order becomes FAILED
```

Payment is never attempted because the workflow stops before payment.

The failure reason is:

```text
INSUFFICIENT_STOCK
```

### Failure: payment declined after stock reservation

Flow:

```text
order.created
   -> inventory.reserved
   -> payment.failed
   -> order becomes FAILED
   -> inventory releases reserved stock
   -> inventory.released
```

The failure reason is:

```text
PAYMENT_DECLINED
```

This demonstrates compensation. Stock is not permanently lost because payment failed.

### Failure: temporary consumer error

When a consumer throws an exception:

1. The original message is not silently lost.
2. The message is republished to a retry queue.
3. The retry count increases.
4. The message receives exponential backoff.
5. After the retry limit is reached, the message moves to a parked queue.

Default delays are approximately:

```text
5 seconds -> 10 seconds -> 20 seconds
```

A parked message can be inspected manually through RabbitMQ.

### Failure: duplicate event delivery

RabbitMQ can redeliver a message. Each event has a unique `event_id`.

Before processing business logic, a consumer attempts to record that event ID in the `processed_events` collection. If the event was already processed, the consumer skips it.

This makes handlers idempotent.

### Failure: service starts before RabbitMQ

Docker health checks and `depends_on` conditions help order startup, but the application may still start during the small window before RabbitMQ accepts connections. The services use robust RabbitMQ connections, and restarting the application containers after the broker becomes healthy resolves this startup race.

### Failure: process crashes after database write but before event publish

This is a known limitation. MongoDB writes and RabbitMQ publishes are not one atomic operation.

The production-grade solution is a transactional outbox:

```text
Business update + outgoing event
          |
          v
      MongoDB outbox
          |
          v
    Background relay
          |
          v
       RabbitMQ
```

The outbox is documented as a future improvement because it requires additional MongoDB replica-set infrastructure and a relay process.

## 9. Data Consistency and Concurrency

Inventory reservation uses an atomic guarded MongoDB update:

```text
Only update a stock document when available_qty >= requested_qty
```

This prevents two concurrent orders from both successfully reserving the same last unit.

The repository also guards release and rollback operations with reserved-quantity checks so stock cannot be over-released.

A concurrent regression test attempts more reservations than the stock allows. It verifies that only the available quantity succeeds and that stock never becomes negative.

## 10. Reliability Features Added

The project was extended in several steps.

### Step 1: CI/CD

Added GitHub Actions in `.github/workflows/ci.yml`.

The workflow:

- Runs shared tests
- Runs each service test suite separately
- Builds Docker images
- Starts infrastructure
- Starts application services
- Waits for health checks
- Runs integration tests
- Prints logs when a job fails
- Cleans up containers

### Step 2: structured logs and correlation IDs

Added:

- JSON log formatting
- `X-Correlation-ID` request header support
- Correlation ID propagation through RabbitMQ events
- Correlation ID restoration in consumers
- Response correlation headers

### Step 3: metrics

Added Prometheus metrics for:

- HTTP request count
- HTTP request duration
- Published events
- Consumed events
- Handler failures
- Scheduled retries
- Parked messages

Metrics endpoints:

```text
http://localhost:8001/metrics
http://localhost:8002/metrics
http://localhost:8003/metrics
```

### Step 4: concurrency-safe inventory

Added atomic reservation behavior and concurrent overselling tests.

### Step 5: admin authentication

Protected all `/admin/*` endpoints with the `X-Admin-API-Key` header.

The key is configured by `ADMIN_API_KEY`.

### Step 6: operations dashboard

Added the `web-ui` service with:

- Service health status
- Guided order scenarios
- Live stock view
- Recent order history
- Payment results
- KPI cards
- Search and status filters
- Clickable order details
- Step-by-step order timeline
- Advanced admin controls

Dashboard URL:

```text
http://localhost:8080
```

### Step 7: free deployment preparation

Added:

- Optional hosted MongoDB connection string
- Optional hosted RabbitMQ connection string
- Configurable CORS origins
- Runtime frontend API URLs
- `render.yaml` blueprint
- `DEPLOY_FREE.md` deployment guide

## 11. Local Setup

### Start the project

From the repository root:

```powershell
docker compose up --build
```

Or run in the background:

```powershell
docker compose up --build -d
```

### Open the dashboard

```text
http://localhost:8080
```

### Useful URLs

```text
Order health:     http://localhost:8001/health
Inventory health: http://localhost:8002/health
Payment health:   http://localhost:8003/health
RabbitMQ UI:      http://localhost:15672
Metrics:          http://localhost:8001/metrics
```

### Stop the project

```powershell
docker compose down
```

### Run unit tests

The test suites are intentionally run separately because every service has an `app` package name:

```powershell
py -3.11 -m pytest shared/tests
py -3.11 -m pytest order-service/tests
py -3.11 -m pytest inventory-service/tests
py -3.11 -m pytest payment-service/tests
```

### Run integration tests

Keep Docker Compose running:

```powershell
py -3.11 -m pytest integration-tests
```

## 12. API Examples

### Create a successful order

```powershell
$body = '{"customer_id":"cust-1","items":[{"sku":"SKU-1","qty":1}],"amount_cents":1000}'

Invoke-RestMethod -Method Post `
  -Uri http://localhost:8001/orders `
  -ContentType "application/json" `
  -Body $body
```

### Force a payment failure

```powershell
$body = '{"customer_id":"cust-1","items":[{"sku":"SKU-1","qty":1}],"amount_cents":2000,"force_payment_failure":true}'

Invoke-RestMethod -Method Post `
  -Uri http://localhost:8001/orders `
  -ContentType "application/json" `
  -Body $body
```

### Read protected inventory data

```powershell
curl.exe -H "X-Admin-API-Key: local-admin-key" http://localhost:8002/admin/stock
```

### Reset demo stock

```powershell
curl.exe -X POST `
  -H "X-Admin-API-Key: local-admin-key" `
  http://localhost:8002/admin/reset-stock
```

## 13. Problems Faced During Development

### Git was not recognized

The local machine did not have Git available on PATH. Git was installed and PowerShell was restarted before cloning.

### Docker could not connect to its engine

The Docker CLI was installed, but Docker Desktop was not running. Starting Docker Desktop and waiting for the engine fixed the named-pipe error.

### Compose configuration file was not found

The command was first run from the parent `Projects` directory. Docker Compose searches the current directory for `docker-compose.yml`, so the command had to be run inside `event-driven-order-saga`.

### Application services exited while RabbitMQ was starting

MongoDB and RabbitMQ containers were healthy, but the application containers had attempted to connect before RabbitMQ accepted connections. Restarting the application services after the broker became healthy resolved the startup race.

### Local workspace and cloned repository were different

The VS Code workspace initially showed a GitHub virtual filesystem copy, while Docker used the local clone under `Desktop\Projects`. Changes had to be applied to the local clone used by Docker.

### Tests collided across services

Each service uses an `app` package. Running every test directory in one pytest collection process can cause module collisions, so the suites are run independently.

### Existing tests did not match a required event field

Two order tests constructed `InventoryReservedPayload` without `amount_cents`, even though the model required it. The tests were corrected to use the order amount.

### Authentication initially broke integration setup

After admin endpoints were protected, integration fixtures that reset or read stock returned `401`. The test requests were updated to send `X-Admin-API-Key`.

### Browser showed an old UI version

The browser had cached an older dashboard tab. Opening a fresh URL with a query-string version confirmed the newly built UI.

### Free deployment has infrastructure limitations

The complete stack needs multiple application services, MongoDB, and RabbitMQ. A single free platform may not provide all of them. The deployment preparation therefore separates application hosting from managed database and broker providers.

## 14. Current Known Limitations

- No transactional outbox yet
- No central Prometheus server or Grafana dashboard
- Free hosted services may sleep
- Payment simulation is deterministic, not a real payment provider
- The dashboard is intended for demonstration, not a customer-facing production UI
- Local default admin key must be replaced before any public deployment
- Hosted MongoDB and RabbitMQ must be configured separately

## 15. Suggested Future Improvements

1. Implement a transactional outbox.
2. Add a real Prometheus and Grafana deployment.
3. Add rate limiting and stronger authentication.
4. Add API versioning such as `/api/v1/orders`.
5. Add OpenAPI examples and generated client documentation.
6. Add load tests and publish measured latency results.
7. Add distributed tracing with OpenTelemetry.
8. Add notification service for email or SMS events.
9. Add database backup and recovery procedures.
10. Add a production deployment with private networking and managed secrets.

## 16. Resume Description

> Built a Dockerized event-driven order-processing saga using FastAPI, RabbitMQ, MongoDB, and a responsive operations dashboard. Implemented choreography-based microservices, idempotent consumers, exponential retry with parked dead-letter queues, compensation for payment failures, correlation IDs, Prometheus metrics, API-key-protected admin endpoints, concurrency-safe inventory reservations, GitHub Actions CI, and end-to-end integration tests.

## 17. Short Interview Explanation

> This project processes an order across three independent services. The order service publishes an event, inventory reserves stock, and payment decides whether the order succeeds. If payment fails after inventory reservation, inventory consumes the failure event and releases the stock. RabbitMQ provides asynchronous communication, MongoDB stores service-owned data, idempotency prevents duplicate processing, retries handle temporary errors, and Docker Compose runs the complete system locally. The dashboard makes the event flow visible.
