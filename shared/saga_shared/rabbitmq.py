"""RabbitMQ helpers: a Publisher, and a ResilientConsumer implementing
retry-with-backoff + a dead-letter "parked" queue.

Topology per consumed (queue_name, routing_key) pair:

    saga.events (topic exchange)
        -> <queue_name>            main queue, bound to routing_key
        -> <queue_name>.retry      no consumer; x-dead-letter-exchange back to
                                    saga.events with x-dead-letter-routing-key
                                    = routing_key, so expired messages land
                                    back in the main queue automatically
        -> <queue_name>.parked     no consumer; permanent DLQ for operator/
                                    demo inspection

On handler failure, instead of relying on AMQP-level nack+DLX (which would
need a ladder of TTL queues to get exponential backoff), the consumer
republishes the message to the retry queue itself with an incremented
``x-retry-count`` header and a per-message ``expiration`` matching the
current backoff step. This keeps the whole retry ladder to two extra queues
per consumed event type instead of one queue per backoff step.
"""
from __future__ import annotations

import json
import logging
from typing import Awaitable, Callable

import aio_pika
from aio_pika import ExchangeType, Message
from aio_pika.abc import AbstractChannel, AbstractIncomingMessage, AbstractQueue

from .events import EventEnvelope

logger = logging.getLogger(__name__)

EXCHANGE_NAME = "saga.events"
RETRY_COUNT_HEADER = "x-retry-count"

Handler = Callable[[dict], Awaitable[None]]


async def connect(rabbitmq_url: str) -> aio_pika.abc.AbstractRobustConnection:
    return await aio_pika.connect_robust(rabbitmq_url)


def compute_retry_decision(
    retry_count: int, max_retries: int, base_delay_ms: int
) -> tuple[str, int | None]:
    """Pure decision function, no I/O - kept separate so it's unit-testable
    without a running broker.

    Returns ("retry", delay_ms) while attempts remain, else ("park", None).
    """
    if retry_count < max_retries:
        return "retry", base_delay_ms * (2**retry_count)
    return "park", None


class Publisher:
    def __init__(self, channel: AbstractChannel):
        self._channel = channel
        self._exchange: aio_pika.abc.AbstractExchange | None = None

    async def _get_exchange(self) -> aio_pika.abc.AbstractExchange:
        if self._exchange is None:
            self._exchange = await self._channel.declare_exchange(
                EXCHANGE_NAME, ExchangeType.TOPIC, durable=True
            )
        return self._exchange

    async def publish(self, routing_key: str, envelope: EventEnvelope) -> None:
        exchange = await self._get_exchange()
        message = Message(
            body=envelope.model_dump_json().encode(),
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        )
        await exchange.publish(message, routing_key=routing_key)
        logger.info(
            "published event_id=%s event_type=%s routing_key=%s",
            envelope.event_id,
            envelope.event_type,
            routing_key,
        )


class ResilientConsumer:
    def __init__(
        self,
        channel: AbstractChannel,
        queue_name: str,
        routing_key: str,
        handler: Handler,
        max_retries: int = 3,
        base_delay_ms: int = 5000,
    ):
        self._channel = channel
        self._queue_name = queue_name
        self._routing_key = routing_key
        self._handler = handler
        self._max_retries = max_retries
        self._base_delay_ms = base_delay_ms
        self.retry_queue_name = f"{queue_name}.retry"
        self.parked_queue_name = f"{queue_name}.parked"

    async def setup(self) -> AbstractQueue:
        exchange = await self._channel.declare_exchange(
            EXCHANGE_NAME, ExchangeType.TOPIC, durable=True
        )
        await self._channel.declare_queue(self.parked_queue_name, durable=True)
        await self._channel.declare_queue(
            self.retry_queue_name,
            durable=True,
            arguments={
                "x-dead-letter-exchange": EXCHANGE_NAME,
                "x-dead-letter-routing-key": self._routing_key,
            },
        )
        main_queue = await self._channel.declare_queue(self._queue_name, durable=True)
        await main_queue.bind(exchange, routing_key=self._routing_key)
        return main_queue

    async def _republish(
        self,
        target_queue_name: str,
        message: AbstractIncomingMessage,
        retry_count: int,
        expiration_ms: int | None,
    ) -> None:
        headers = dict(message.headers or {})
        headers[RETRY_COUNT_HEADER] = retry_count
        new_message = Message(
            body=message.body,
            headers=headers,
            content_type=message.content_type,
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            expiration=str(expiration_ms) if expiration_ms is not None else None,
        )
        await self._channel.default_exchange.publish(
            new_message, routing_key=target_queue_name
        )

    async def _on_message(self, message: AbstractIncomingMessage) -> None:
        retry_count = int((message.headers or {}).get(RETRY_COUNT_HEADER, 0))
        try:
            payload = json.loads(message.body)
            await self._handler(payload)
        except Exception:
            logger.exception(
                "handler failed queue=%s retry_count=%s", self._queue_name, retry_count
            )
            decision, delay_ms = compute_retry_decision(
                retry_count, self._max_retries, self._base_delay_ms
            )
            if decision == "retry":
                await self._republish(
                    self.retry_queue_name, message, retry_count + 1, delay_ms
                )
            else:
                await self._republish(self.parked_queue_name, message, retry_count, None)
                logger.error(
                    "parked message queue=%s after %s retries", self._queue_name, retry_count
                )
        await message.ack()

    async def start(self) -> AbstractQueue:
        queue = await self.setup()
        await self._channel.set_qos(prefetch_count=10)
        await queue.consume(self._on_message)
        return queue
