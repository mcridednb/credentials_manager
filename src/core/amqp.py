from typing import Union

from django.conf import settings
from kombu import Connection, Exchange, Queue


def publish(queue_name, account: Union[dict, list]):
    with Connection(settings.AMQP_URL) as connection:
        queue = Queue(
            name=queue_name,
            exchange=Exchange("accounts", "direct", durable=True),
            routing_key=queue_name,
        )
        connection.Producer(serializer="json").publish(
            body=account,
            exchange=queue.exchange,
            routing_key=queue.routing_key,
            declare=[queue],
            timeout=60,
        )


def consume(queue_name, ack=True):
    with Connection(settings.AMQP_URL) as connection:
        q = connection.SimpleQueue(Queue(
            name=queue_name,
            exchange=Exchange("accounts", "direct", durable=True),
            routing_key=queue_name,
        ))
        try:
            msg = q.get(block=False)
        except q.Empty:
            return None
        else:
            if ack:
                msg.ack()
                return msg.payload
            else:
                return msg
