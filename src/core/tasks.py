import json
from typing import Union

from django.db.models import F, Q
from django.utils import timezone
from loguru import logger

from conf.celery import app
from core import amqp
from core.models import (
    CredentialsProxy, Proxy, CredentialsStatistics, ProxyCounter,
)
from core.serializers import CredentialsProxySerializer


@app.task
def update_account_status(credentials_proxy_id, status):
    credentials_proxy = CredentialsProxy.objects.select_related(
        "credentials__network"
    ).get(
        id=credentials_proxy_id
    )
    credentials_proxy.status = status
    credentials_proxy.time_of_sent = timezone.now()
    credentials_proxy.counter += 1
    credentials_proxy.start_time_of_use = timezone.now()
    credentials_proxy.status_updated = timezone.now()
    credentials_proxy.save()
    proxy_counter, _ = ProxyCounter.objects.get_or_create(
        network=credentials_proxy.credentials.network,
        proxy=credentials_proxy.proxy,
    )
    proxy_counter.counter += 1
    proxy_counter.save()
    logger.info(
        f"cred: {credentials_proxy_id} - CHANGED STATUS TO '{status}'"
    )


@app.task(name="load_accounts_to_queue")
def load_accounts_to_queue(**kwargs):
    credentials_proxies = CredentialsProxy.objects.filter(
        status=CredentialsProxy.Status.AVAILABLE,
        enable=True,
    ).exclude(
        credentials__network__title="ok"
    ).select_related(
        "credentials",
        "credentials__network",
        "proxy",
    )

    for credentials_proxy in credentials_proxies:
        # if (
        #     credentials_proxy.credentials.network.title == "facebook"
        #     and (not credentials_proxy.proxy.mobile)
        # ):
        #     credentials_proxy_count = CredentialsProxy.objects.filter(
        #         credentials__network=credentials_proxy.credentials.network,
        #         proxy=credentials_proxy.proxy
        #     ).filter(
        #         Q(status=CredentialsProxy.Status.SENT) |
        #         Q(status=CredentialsProxy.Status.IN_QUEUE)
        #     ).count()
        #     try:
        #         proxy_counter, _ = ProxyCounter.objects.get_or_create(
        #             network=credentials_proxy.credentials.network,
        #             proxy=credentials_proxy.proxy,
        #         )
        #     except Exception:
        #         proxy_counter, _ = ProxyCounter.objects.get(
        #             network=credentials_proxy.credentials.network,
        #             proxy=credentials_proxy.proxy,
        #         )
        #     if credentials_proxy_count > proxy_counter.counter // 10:
        #         continue

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
        enable=True,
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
