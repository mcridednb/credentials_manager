import json
from typing import Union

from django.db.models import F, Q
from django.utils import timezone

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


@app.task(name="load_accounts_to_queue")
def load_accounts_to_queue(**kwargs):
    credentials_proxies = CredentialsProxy.objects.filter(
        status=CredentialsProxy.Status.AVAILABLE
    ).select_related("credentials", "credentials__network")

    for credentials_proxy in credentials_proxies:
        amqp.publish(
            credentials_proxy.credentials.network.title,
            CredentialsProxySerializer(credentials_proxy).data
        )

    credentials_proxies.update(status=CredentialsProxy.Status.IN_QUEUE)


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


@app.task
def update_credentials_proxy_info(
    credentials_proxy_id: int,
    cookies: Union[list, dict],
    request_count: dict,
    limit: dict,
    status: str,
    description: str,
):
    waiting_delta = 60 * 60  # 1 hour

    if status == CredentialsProxy.Status.TEMPORARILY_BANNED:
        waiting_delta = waiting_delta * 2  # 2 hours

    credentials_proxy = CredentialsProxy.objects.select_related(
        "credentials", "credentials__network"
    ).get(id=credentials_proxy_id)

    if cookies is not None and isinstance(cookies, str):
        cookies = json.loads(cookies)

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
