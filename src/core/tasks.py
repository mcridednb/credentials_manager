from django.db.models import F, Q
from django.utils import timezone

from conf.celery import app
from core import amqp
from core.models import CredentialsProxy, Proxy
from core.serializers import CredentialsProxySerializer


@app.task
def update_account_status(credentials_proxy_id, status):
    CredentialsProxy.objects.filter(id=credentials_proxy_id).update(
        status=status,
        time_of_sent=timezone.now(),
        counter=F('counter') + 1,
    )


@app.task(name="load_accounts_to_queue")
def load_accounts_to_queue(**kwargs):
    credentials_proxies = CredentialsProxy.objects.filter(
        status=CredentialsProxy.Status.AVAILABLE
    )
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
