from django.utils import timezone

from conf.celery import app
from core.models import Credentials, CredentialsProxy, Proxy


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
        status=CredentialsProxy.Status.WAITING
    )
    for credentials_proxy in credentials_proxies:
        if (
            timezone.now() - credentials_proxy.status_updated
        ).total_seconds() > credentials_proxy.waiting_delta:
            credentials_proxy.status = CredentialsProxy.Status.AVAILABLE
            credentials_proxy.save()


@app.task
def generate_credentials_proxy(**kwargs):
    credentials = Credentials.objects.filter(enable=True)
    for credential in credentials:
        # Если связка этого аккаунта с прокси существует, то пропускаем
        if CredentialsProxy.objects.filter(credentials=credential):
            continue

        # Ищем прокси, которые не используются в той-же соц. сети
        exclude_proxy_ids = CredentialsProxy.objects.filter(
            credentials__network=credential.network,
        ).values("proxy_id")

        proxy = Proxy.objects.exclude(
            id__in=exclude_proxy_ids
        ).order_by("?").first()

        if proxy:
            CredentialsProxy.objects.create(
                credentials=credential, proxy=proxy
            )
