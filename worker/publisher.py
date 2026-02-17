import json
import threading
from typing import Any

import pika

from env import (
    RABBITMQ_DLQ,
    RABBITMQ_MAIN_QUEUE,
    RABBITMQ_URL,
)

_thread_local = threading.local()


def _ensure_queues(channel: pika.channel.Channel) -> None:
    channel.queue_declare(queue=RABBITMQ_MAIN_QUEUE, durable=True)
    channel.queue_declare(queue=RABBITMQ_DLQ, durable=True)


def _get_publish_channel() -> pika.channel.Channel:
    if not getattr(_thread_local, "channel", None) or _thread_local.channel.is_closed:
        conn = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
        ch = conn.channel()
        _ensure_queues(ch)
        _thread_local.conn = conn
        _thread_local.channel = ch
    return _thread_local.channel


def _publish_to_main(payload: dict[str, Any]) -> None:
    ch = _get_publish_channel()
    ch.basic_publish(
        exchange="",
        routing_key=RABBITMQ_MAIN_QUEUE,
        body=json.dumps(payload).encode(),
        properties=pika.BasicProperties(delivery_mode=2),
    )


def _publish_to_dlq(body: bytes) -> None:
    ch = _get_publish_channel()
    ch.basic_publish(
        exchange="",
        routing_key=RABBITMQ_DLQ,
        body=body,
        properties=pika.BasicProperties(delivery_mode=2),
    )

