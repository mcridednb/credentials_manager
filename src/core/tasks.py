import json
from typing import Union

from django.db.models import F, Q
from django.utils import timezone
from loguru import logger

from conf.celery import app
from core import amqp
from core.models import CredentialsProxy, Proxy, CredentialsStatistics
from core.serializers import CredentialsProxySerializer


@app.task
def update_account_status(credentials_proxy_id, status):
    CredentialsProxy.objects.filter(id=credentials_proxy_id).update(
        status=status,
        time_of_sent=timezone.now(),
        counter=F('counter') + 1,
        start_time_of_use=timezone.now(),
    )
    logger.info(
        f"cred: {credentials_proxy_id} - CHANGED STATUS TO '{status}'"
    )


@app.task(name="load_accounts_to_queue")
def load_accounts_to_queue(**kwargs):
    credentials_proxies = CredentialsProxy.objects.filter(
        status=CredentialsProxy.Status.AVAILABLE
    ).exclude(
        credentials__network__title="ok"
    ).select_related("credentials", "credentials__network")

    for credentials_proxy in credentials_proxies:
        credentials_proxy.status = CredentialsProxy.Status.IN_QUEUE
        credentials_proxy.save()
        logger.info(
            f"cred: {credentials_proxy.id} - CHANGED STATUS TO 'IN_QUEUE'"
        )
        amqp.publish(
            credentials_proxy.credentials.network.title,
            CredentialsProxySerializer(credentials_proxy).data,
        )
        logger.info(
            f"cred: {credentials_proxy.id} "
            f"- SEND ACCOUNT TO QUEUE "
            f"({credentials_proxy.credentials.network.title})"
        )


@app.task(name="load_ok_accounts_to_queue")
def load_ok_accounts_to_queue(**kwargs):
    proxies = CredentialsProxy.objects.filter(
        status=CredentialsProxy.Status.AVAILABLE,
        credentials__network__title="ok",
    ).values_list("proxy__ip", flat=True)

    for proxy_ip in set(proxies):
        credentials_proxy = CredentialsProxy.objects.filter(
            proxy__ip=proxy_ip,
            credentials__network__title="ok",
            status=CredentialsProxy.Status.AVAILABLE,
        ).select_related("credentials", "credentials__network")

        data = CredentialsProxySerializer(credentials_proxy, many=True).data
        credentials_proxy.update(status=CredentialsProxy.Status.IN_QUEUE)

        for account in credentials_proxy:
            logger.info(f"cred: {account.id} - CHANGED STATUS TO 'IN_QUEUE'")

        amqp.publish("ok", data)
        for account in credentials_proxy:
            logger.info(f"cred: {account.id} - SEND ACCOUNT TO QUEUE (ok)")


@app.task(name="update_proxy_statuses")
def update_proxy_statuses(**kwargs):
    proxies = Proxy.objects.filter(enable=True)
    if kwargs.get('all'):
        proxies = Proxy.objects.all()

    for proxy in proxies:
        proxy.update_status()


@app.task(name="update_credentials_proxy_statuses")
def update_credentials_proxy_statuses(**kwargs):
    credentials_proxies = CredentialsProxy.objects.filter(
        Q(status=CredentialsProxy.Status.WAITING) |
        Q(status=CredentialsProxy.Status.TEMPORARILY_BANNED)
    )
    for credentials_proxy in credentials_proxies:
        if (
            timezone.now() - credentials_proxy.status_updated
        ).total_seconds() > credentials_proxy.waiting_delta:
            credentials_proxy.status = CredentialsProxy.Status.AVAILABLE
            credentials_proxy.save()
            logger.info(
                f"cred: {credentials_proxy.id} - CHANGE STATUS TO 'AVAILABLE'"
            )


@app.task
def update_credentials_proxy_info(
    credentials_proxy_id: int,
    cookies: Union[list, dict],
    request_count: dict,
    limit: dict,
    status: str,
    description: str,
):
    credentials_proxy = CredentialsProxy.objects.select_related(
        "credentials", "credentials__network"
    ).get(id=credentials_proxy_id)

    if cookies is not None and isinstance(cookies, str):
        cookies = json.loads(cookies)

    waiting_delta = 60 * 60  # 1 hour

    if credentials_proxy.counter < 20:
        waiting_delta = 60 * 30  # 30 minutes

    if status == CredentialsProxy.Status.TEMPORARILY_BANNED:
        waiting_delta = waiting_delta * 2  # 2 hours

    credentials_proxy.cookies = cookies
    credentials_proxy.status = status
    credentials_proxy.status_description = description
    credentials_proxy.waiting_delta = waiting_delta
    credentials_proxy.save()

    credentials = credentials_proxy.credentials

    CredentialsStatistics.objects.create(
        credentials_proxy=credentials_proxy,
        account_title=f"{credentials.network.title}_{credentials.login}",
        start_time_of_use=credentials_proxy.start_time_of_use,
        end_time_of_use=timezone.now(),
        request_count=request_count,
        limit=limit,
        result_status=status,
        status_description=description,
    )
    logger.info(
        f"cred: {credentials_proxy.id} "
        f"- RECEIVE STATISTICS WITH STATUS '{status}' "
        f"DESCRIPTION: {description}"
    )
