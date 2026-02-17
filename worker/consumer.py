import logging
import pika

from env import (
    RABBITMQ_DLQ,
    RABBITMQ_MAIN_QUEUE,
    RABBITMQ_URL,
)
from process import _process_main_message, _process_dlq_message
from publisher import _ensure_queues

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _run_main_consumer() -> None:
    conn = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
    ch = conn.channel()
    _ensure_queues(ch)
    ch.basic_qos(prefetch_count=1)

    def on_message(channel, method, properties, body):
        try:
            _process_main_message(body)
            channel.basic_ack(method.delivery_tag)
        except Exception as e:
            logger.exception("Main consumer error: %s", e)
            channel.basic_nack(method.delivery_tag, requeue=False)

    ch.basic_consume(queue=RABBITMQ_MAIN_QUEUE, on_message_callback=on_message)
    logger.info("Consuming from %s", RABBITMQ_MAIN_QUEUE)
    ch.start_consuming()


def _run_dlq_consumer() -> None:
    conn = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
    ch = conn.channel()
    _ensure_queues(ch)
    ch.basic_qos(prefetch_count=1)

    def on_message(channel, method, properties, body):
        try:
            _process_dlq_message(body)
            channel.basic_ack(method.delivery_tag)
        except Exception as e:
            logger.exception("DLQ consumer error: %s", e)
            channel.basic_nack(method.delivery_tag, requeue=False)

    ch.basic_consume(queue=RABBITMQ_DLQ, on_message_callback=on_message)
    logger.info("Consuming from %s", RABBITMQ_DLQ)
    ch.start_consuming()
