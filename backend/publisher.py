import pika
from config import get_settings

settings = get_settings()

RABBITMQ_URL = settings.RABBITMQ_URL
RABBITMQ_MAIN_QUEUE = settings.RABBITMQ_MAIN_QUEUE

def _get_connection():
    params = pika.URLParameters(RABBITMQ_URL)
    return pika.BlockingConnection(params)

def _publish_to_main_queue(body: bytes) -> None:
    conn = _get_connection()
    ch = conn.channel()
    ch.queue_declare(queue=RABBITMQ_MAIN_QUEUE, durable=True)
    ch.basic_publish(exchange="", routing_key=RABBITMQ_MAIN_QUEUE, body=body)
    ch.close()
    conn.close()
