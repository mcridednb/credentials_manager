from django.conf import settings
from kombu import Connection, Exchange, Queue

accounts_exchange = Exchange("accounts", 'direct', durable=True)
connection = Connection(settings.AMQP_URL)
producer = connection.Producer(serializer='json')


def _get_queue(queue_name):
    return Queue(
        name=queue_name,
        exchange=accounts_exchange,
        routing_key=queue_name,
    )


def _get_simple_queue(queue_name):
    return connection.SimpleQueue(_get_queue(queue_name))


def publish(queue_name, account: dict):
    producer.publish(
        body=account,
        exchange=accounts_exchange,
        routing_key=queue_name,
        declare=[_get_queue(queue_name)],
    )


def consume(queue_name):
    q = _get_simple_queue(queue_name)
    try:
        msg = q.get(block=False)
    except q.Empty:
        return None
    else:
        msg.ack()
        return msg.payload
