# Order Saga — Event-Driven Microservices (FastAPI + RabbitMQ + MongoDB)

A choreography-based order processing saga split across three independent FastAPI services that communicate exclusively through RabbitMQ. Built to demonstrate asynchronous, event-driven service decomposition with production-style resilience: retry-with-backoff, dead-letter queues, idempotent consumers, and saga compensation — as a companion to a Java/Spring Boot resume, not a replacement for it.

## Why this exists

Most of my prior work is synchronous request/response on the JVM (Spring Boot + REST + Prometheus/Actuator). This project is deliberately a different stack (Python/FastAPI/RabbitMQ/MongoDB) and a different problem shape (asynchronous, eventually-consistent, multi-service) — the kind of system design question ("what happens when step 3 fails after step 2 already succeeded?") that doesn't come up in a single monolith.

## Architecture

Three services, one topic exchange, no orchestrator:

```
                 saga.events (topic exchange)
                          │
   POST /orders            │ order.created
order-service ───────────────────────────▶ inventory-service
     ▲   │                                      │
     │   │ inventory.reserved                   │ inventory.reservation_failed
     │   └──────────────────────┬───────────────┘
     │                          ▼
     │                  payment-service
     │                          │
     │   payment.completed /   │
     └───── payment.failed ─────┘
                          │
                          │ payment.failed (also consumed by inventory-service
                          ▼  to release stock — compensation)
                  inventory-service
```

- **order-service** — REST entrypoint (`POST /orders`, `GET /orders/{id}`), owns order status/history, has no business logic beyond state transitions.
- **inventory-service** — owns stock, reserves/releases it, seeds a small fixed catalog on startup.
- **payment-service** — simulates a payment decision deterministically (see below), owns payment records.

This is **choreography, not orchestration**: there is no 4th "saga coordinator" service telling the others what to do. Each service reacts to events and publishes its own. That's the right call at 3 services — a coordinator would be pure overhead here — but it doesn't scale cleanly past ~5-6 services or complex branching sagas, where centralizing the flow in an orchestrator (e.g. Temporal, or a hand-rolled state machine service) becomes worth the extra hop. Worth saying out loud in an interview, not worth building for this scope.

### Saga trace

Order status moves `PENDING → INVENTORY_RESERVED → CONFIRMED`, or diverts to `FAILED` with a `failure_reason`.

- **Happy path**: `order.created` → inventory reserves stock → `inventory.reserved` → payment approves → `payment.completed` → order `CONFIRMED`.
- **Compensation path** (payment declines *after* stock was reserved): `payment.failed` is consumed by **both** order-service (marks the order `FAILED/PAYMENT_DECLINED` immediately) **and** inventory-service (independently releases the reservation and publishes `inventory.released`, which order-service just appends to its audit history since the order is already terminal). This is the concrete answer to "what if step 3 fails after step 2 succeeded" — no coordinator needed, each service knows how to undo its own step.
- **Short-circuit path** (insufficient stock): `inventory.reservation_failed` → order `FAILED/INSUFFICIENT_STOCK`. Payment-service is never invoked — the saga fails before spending a payment attempt.

Payment approval is **deterministic, not random**: declines if `amount_cents` exceeds `PAYMENT_FAIL_THRESHOLD_CENTS` (default $1000) or if the order sets `force_payment_failure: true`. Random failure simulation makes for an undemoable, unrepeatable system; a deterministic rule makes every scenario reproducible on command.

### RabbitMQ topology

One topic exchange, `saga.events`. Each consumer gets its own queue per event type (not one queue with multiple bindings), so the retry/DLQ wiring below stays a simple 1:1 mapping instead of needing to disambiguate which binding a message failed under.

Per consumer queue `Q`:
- `Q` — the live queue, consumed with `prefetch_count=10` and manual ack.
- `Q.retry` — no consumer; declared with `x-dead-letter-exchange`/`x-dead-letter-routing-key` pointing back at `Q`'s original routing key.
- `Q.parked` — no consumer; permanent dead-letter queue, inspectable via the RabbitMQ management UI.

Retry logic is **application-level**, not a pure AMQP TTL-ladder: a message carries an `x-retry-count` header (default 0). On handler exception, the consumer republishes to `Q.retry` with the header incremented and a per-message `expiration` of `5s * 2^retry_count` (5s → 10s → 20s), then acks the original. When the retry message's TTL expires, RabbitMQ's dead-letter mechanism drops it back into `Q`. After `MAX_RETRIES` (default 3), the message goes to `Q.parked` instead and stays there for manual inspection. Total time-to-park is ~35s — fast enough to demo live without a contrived multi-minute wait.

A single retry queue with a per-message TTL was chosen over a ladder of fixed-TTL queues (5s queue → 10s queue → 20s queue) because it produces the same backoff with one queue instead of three, at the cost of setting `expiration` per-publish instead of per-queue — a straightforward trade since the delay already has to be computed at publish time anyway.

### Idempotency

Every event envelope carries a generated `event_id`. Each service has a `processed_events` collection (`_id = event_id`, TTL index, 30 days). Handler shape: try to insert the event_id first — a duplicate-key error means "already handled, ack and return" — then do the business write, then publish resulting events, then ack.

**Known gap, deliberately not fixed**: the Mongo write and the RabbitMQ publish are not atomic. If the process crashes between them, either the same event could reprocess (fine — that's what the idempotency check is for) or the causal side-effect (the follow-up publish) could be lost even though the local write succeeded. The correct fix is a **transactional outbox**: write the outcome and the outbound event to Mongo in the same transaction, then have a separate relay process actually publish to RabbitMQ from that outbox table. That needs a Mongo replica set (multi-document transactions require one) plus a relay process — disproportionate infrastructure for a 3-service demo. This is intentionally left as the "what would you improve" answer rather than built.

As defense-in-depth beyond event-level dedup, inventory-service's `reservations` collection also has a **unique index on `order_id`**, so a double-reservation is structurally impossible even if event dedup were somehow bypassed.

### Chaos knob for demoing retries

`order.created` accepts an optional `simulate_transient_failure_count`. Inventory-service tracks attempts per `event_id` in a `chaos_attempts` collection (independent of the AMQP retry-count header, so it survives actual message redelivery) and deliberately raises until that many attempts have been made, then succeeds. This makes the retry → backoff → eventual-success path demoable on command instead of relying on an incidental real transient failure.

## Repo layout

```
shared/saga_shared/       installable local package: event schemas, Mongo/RabbitMQ helpers,
                           idempotency helper, the retry/DLQ engine (ResilientConsumer), settings
order-service/            REST API + order status/history owner
inventory-service/        stock owner, reservation/release logic
payment-service/          deterministic payment simulation
integration-tests/        httpx-driven end-to-end tests against the live docker-compose stack
docker-compose.yml
.env.example
```

Each service's Dockerfile is built with `context: .` (the repo root) so it can `COPY shared/` and `pip install` the shared package before installing its own requirements — one shared library, no duplicated retry/DLQ/idempotency logic across services, no monorepo tooling.

## Running it

```
cp .env.example .env
docker compose up --build
```

This brings up RabbitMQ (management UI on http://localhost:15672, guest/guest), MongoDB, and all three services (order 8001, inventory 8002, payment 8003), waiting on health checks in the right order.

```bash
# happy path
curl -X POST localhost:8001/orders -H "Content-Type: application/json" -d '{
  "customer_id": "cust-1",
  "items": [{"sku": "SKU-1", "qty": 2}],
  "amount_cents": 5000
}'

# forced payment decline -> compensation (stock released)
curl -X POST localhost:8001/orders -H "Content-Type: application/json" -d '{
  "customer_id": "cust-1",
  "items": [{"sku": "SKU-1", "qty": 2}],
  "amount_cents": 2000,
  "force_payment_failure": true
}'

# insufficient stock (SKU-5 is seeded with only 2 units)
curl -X POST localhost:8001/orders -H "Content-Type: application/json" -d '{
  "customer_id": "cust-1",
  "items": [{"sku": "SKU-5", "qty": 10}],
  "amount_cents": 1000
}'

# demo the retry/backoff path on command
curl -X POST localhost:8001/orders -H "Content-Type: application/json" -d '{
  "customer_id": "cust-1",
  "items": [{"sku": "SKU-1", "qty": 1}],
  "amount_cents": 1000,
  "simulate_transient_failure_count": 2
}'

curl localhost:8001/orders/<order_id>       # poll status/history
curl -X POST localhost:8002/admin/reset-stock  # reset the demo between runs
```

## Testing

**Unit tests** — no Docker, no network I/O, run per-service with `mongomock-motor` standing in for MongoDB:

```
pytest shared/tests
pytest order-service/tests
pytest inventory-service/tests
pytest payment-service/tests
```

(All 4 suites are run separately — every service's app package is named `app`, so collecting them in a single pytest process would collide on `sys.modules["app"]`. See the comment in `pytest.ini`.)

**Integration tests** — require the full stack up (`docker compose up --build`), then:

```
pip install -r integration-tests/requirements.txt
pytest integration-tests
```

These drive the real REST APIs with `httpx`, poll order status to a terminal state, and for the compensation scenario additionally assert against inventory-service's admin endpoint that stock was actually restored — not just that the order's status field flipped.

## Explicit non-goals

Documented here so they read as deliberate scope decisions, not gaps I didn't notice:

- No orchestrator/saga-coordinator service — choreography suits 3 services; wouldn't past ~5-6 or complex branching.
- No Kafka alongside RabbitMQ — one broker, chosen for AMQP's native per-message TTL/DLX primitives which map directly onto the retry design above.
- No multi-rung TTL-queue ladder — a single retry queue with a per-message TTL achieves the same exponential backoff more simply.
- No Mongo replica set / transactional outbox — see the idempotency section above; the honest trade-off.
- No generic event-bus abstraction or DI framework — three services, one shared library, plain functions.
- No Kubernetes manifests — Docker Compose only.

## A note on numbers

Any latency/throughput numbers claimed for this project (in a resume, README, or interview) are real measurements taken against this specific stack on my own machine, not figures copied from someone else's write-up of a similar architecture. If you don't see benchmark numbers here, it's because I haven't measured them yet, not because they're implied.
