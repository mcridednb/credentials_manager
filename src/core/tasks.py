from django.db.models import Q
from django.utils import timezone
from loguru import logger

from conf.celery import app
from core import amqp
from core.models import Account, Proxy, ProxyCounter
from core.serializers import AccountSerializer


@app.task
def update_account_status(account_id, status):
    account = Account.objects.select_related(
        "network"
    ).get(id=account_id)
    account.status = status
    account.time_of_sent = timezone.now()
    account.counter += 1
    account.start_time_of_use = timezone.now()
    account.save()
    proxy_counter, _ = ProxyCounter.objects.get_or_create(
        network=account.network,
        proxy=account.proxy,
    )
    proxy_counter.counter += 1
    proxy_counter.save()
    logger.info(f"account: {account_id} - CHANGED STATUS TO '{status}'")


@app.task(name="load_accounts_to_queue")
def load_accounts_to_queue(**kwargs):
    accounts = Account.objects.filter(
        status=Account.Status.AVAILABLE,
        enable=True,
    ).exclude(
        network__title="ok"
    ).select_related("network", "proxy",)

    for account in accounts:
        account.status = Account.Status.IN_QUEUE
        account.save()
        logger.info(f"account: {account.id} - CHANGED STATUS TO 'IN_QUEUE'")
        try:
            data = AccountSerializer(account).data
        except ValueError:
            continue
        amqp.publish(account.network.title, data)
        logger.info(
            f"account: {account.id} "
            f"- SEND ACCOUNT TO QUEUE "
            f"({account.network.title})"
        )


@app.task(name="load_ok_accounts_to_queue")
def load_ok_accounts_to_queue(**kwargs):
    proxies = Account.objects.filter(
        status=Account.Status.AVAILABLE,
        network__title="ok",
        enable=True,
    ).values_list("proxy__ip", flat=True)

    for proxy_ip in set(proxies):
        accounts = Account.objects.filter(
            proxy__ip=proxy_ip,
            network__title="ok",
            status=Account.Status.AVAILABLE,
        ).exclude(proxy__isnull=True).select_related("network")

        data = AccountSerializer(accounts, many=True).data
        accounts.update(status=Account.Status.IN_QUEUE)

        for account in accounts:
            logger.info(f"account: {account.id} - CHANGED STATUS TO 'IN_QUEUE'")

        amqp.publish("ok", data)
        for account in accounts:
            logger.info(f"account: {account.id} - SEND ACCOUNT TO QUEUE (ok)")


@app.task(name="update_proxy_statuses")
def update_proxy_statuses(**kwargs):
    proxies = Proxy.objects.filter(enable=True)
    if kwargs.get('all'):
        proxies = Proxy.objects.all()

    for proxy in proxies:
        proxy.update_status()


@app.task(name="update_accounts_statuses")
def update_accounts_statuses(**kwargs):
    accounts = Account.objects.filter(
        Q(status=Account.Status.WAITING) |
        Q(status=Account.Status.TEMPORARILY_BANNED)
    )
    for account in accounts:
        if (
            timezone.now() - account.status_updated
        ).total_seconds() > account.waiting_delta:
            account.status = Account.Status.AVAILABLE
            account.save()
            logger.info(
                f"account: {account.id} - CHANGE STATUS TO 'AVAILABLE'"
            )


@app.task(name="set_proxy_accounts")
def set_proxy_accounts(**kwargs):
    ...
