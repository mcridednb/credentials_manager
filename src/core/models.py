from datetime import datetime, timedelta
import logging
import os

from django.db import models
import requests

from core.utils import check_proxy

logger = logging.getLogger(__name__)


class Network(models.Model):
    title = models.CharField(max_length=255, unique=True)
    dynamic_limits = models.BooleanField(default=False)

    def __str__(self):
        return self.title

    class Meta:
        verbose_name = "сеть"
        verbose_name_plural = "сети"


class ParsingType(models.Model):
    title = models.CharField(max_length=255)
    code = models.CharField(max_length=255, null=True)
    network = models.ForeignKey(
        Network, on_delete=models.CASCADE, related_name='types'
    )
    limit = models.IntegerField(default=0)

    class Meta:
        verbose_name = "ограничение на типы парсинга"
        verbose_name_plural = "ограничения на типы парсинга"


class Credentials(models.Model):
    network = models.ForeignKey(Network, on_delete=models.CASCADE, null=True)

    login = models.CharField(max_length=255)
    password = models.CharField(max_length=255)

    price = models.IntegerField(null=True, blank=True)

    enable = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.network}:{self.login}"

    class Meta:
        verbose_name = "аккаунт"
        verbose_name_plural = "аккаунты"
        constraints = [
            models.UniqueConstraint(
                fields=["network", "login"], name="network_login_constraint"
            )
        ]


class Proxy(models.Model):
    class Type(models.TextChoices):
        SOCKS5 = "socks5"
        HTTP = "http"

    class Status(models.TextChoices):
        AVAILABLE = "available"
        NOT_AVAILABLE = "not_available"
        IP_NOT_EQUAL = "ip_not_equal"

    type = models.CharField(
        max_length=255, choices=Type.choices, default=Type.HTTP
    )

    ip = models.CharField(max_length=255)
    port = models.CharField(max_length=255)

    login = models.CharField(max_length=255, null=True, blank=True)
    password = models.CharField(max_length=255, null=True, blank=True)

    status = models.CharField(
        max_length=255, choices=Status.choices, default=Status.AVAILABLE
    )
    status_updated = models.DateTimeField(auto_now=True)

    expiration_date = models.DateField(null=True, blank=True)
    enable = models.BooleanField(default=True)

    mobile = models.BooleanField(default=False)

    price = models.IntegerField(null=True, blank=True)

    tomorrow_notification = models.BooleanField(default=False)
    today_notification = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.ip}:{self.port}"

    @property
    def url(self):
        if self.type == self.Type.SOCKS5:
            self.type = self.type + "h"
        return f"{self.type}://{self.login}:{self.password}@{self.ip}:{self.port}"

    @staticmethod
    def send_telegram_notification(msg):
        api_token = os.getenv("TELEGRAM_API_TOKEN")
        chat_id = os.getenv("TELEGRAM_CHAT_ID")
        requests.post(
            f'https://api.telegram.org/bot{api_token}/sendMessage',
            json={'chat_id': chat_id, 'text': msg}
        )

    def check_date(self):
        if self.expiration_date == (datetime.today() + timedelta(days=1)).date():
            if not self.tomorrow_notification:
                self.send_telegram_notification(f"Завтра заканчиваются прокси {self.ip}")
                self.tomorrow_notification = True

        if self.expiration_date == datetime.today().date():
            if not self.today_notification:
                self.send_telegram_notification(f"Сегодня заканчиваются прокси {self.ip}")
                self.today_notification = True

    def update_status(self):
        try:
            result_ip = check_proxy(self.url)
        except Exception as e:
            self.status = self.Status.NOT_AVAILABLE
            self.enable = False
            logger.warning(f"Something went wrong with ip: {self.ip}: {e}")
        else:
            if self.ip == result_ip:
                self.status = self.Status.AVAILABLE
            else:
                self.status = self.Status.IP_NOT_EQUAL
            self.check_date()
        finally:
            self.save()

    class Meta:
        verbose_name = "прокси"
        verbose_name_plural = "прокси"
        constraints = [
            models.UniqueConstraint(
                fields=["ip", "port"], name="ip_port_constraint"
            )
        ]


class ProxyCounter(models.Model):
    network = models.ForeignKey(Network, on_delete=models.CASCADE)
    proxy = models.ForeignKey(
        Proxy, related_name="counters", on_delete=models.CASCADE
    )
    counter = models.IntegerField(default=0)

    class Meta:
        verbose_name = "счетчик прокси"
        verbose_name_plural = "счетчик прокси"
        constraints = [
            models.UniqueConstraint(
                fields=["network", "proxy"], name="network_proxy_constraint"
            )
        ]


class CredentialsProxy(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = 'available'
        IN_QUEUE = 'in_queue'
        SENT = 'sent'
        NOT_AVAILABLE = 'not_available'
        PROXY_ERROR = 'proxy_error'
        LOGIN_FAILED = 'login_failed'
        TEMPORARILY_BANNED = 'temporarily_banned'
        BANNED = 'banned'
        WAITING = 'waiting'

    credentials = models.OneToOneField(
        Credentials, on_delete=models.CASCADE
    )
    proxy = models.ForeignKey(
        Proxy, on_delete=models.DO_NOTHING, related_name="credentials_proxy"
    )

    status = models.CharField(
        max_length=255, choices=Status.choices, default=Status.AVAILABLE
    )
    status_description = models.CharField(max_length=1024, null=True, blank=True)
    status_updated = models.DateTimeField(auto_now=True)

    waiting_delta = models.IntegerField(default=60 * 60, help_text="In seconds")

    enable = models.BooleanField(default=True)

    time_of_sent = models.DateTimeField(null=True, blank=True)
    start_time_of_use = models.DateTimeField(null=True, blank=True)

    cookies = models.JSONField(null=True, blank=True)

    counter = models.IntegerField(default=0)

    token = models.CharField(max_length=255, null=True)

    def __str__(self):
        return str(self.credentials)

    class Meta:
        verbose_name = "прокси-аккаунт"
        verbose_name_plural = "прокси-аккаунты"
        constraints = [
            models.UniqueConstraint(
                fields=["credentials", "proxy"],
                name="credentials_proxy_constraint",
            )
        ]


class CredentialsStatistics(models.Model):
    class Status(models.TextChoices):
        NOT_AVAILABLE = 'not_available'
        LOGIN_FAILED = 'login_failed'
        TEMPORARILY_BANNED = 'temporarily_banned'
        BANNED = 'banned'
        WAITING = 'waiting'

    credentials_proxy = models.ForeignKey(
        CredentialsProxy,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="statistics"
    )
    account_title = models.CharField(max_length=255, null=True)
    start_time_of_use = models.DateTimeField()
    end_time_of_use = models.DateTimeField()
    request_count = models.JSONField(null=True)
    limit = models.JSONField(null=True)
    result_status = models.CharField(max_length=255, choices=Status.choices)
    status_description = models.TextField(null=True, blank=True)

    proxy = models.ForeignKey(
        Proxy,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="statistics"
    )

    class Meta:
        verbose_name = "статистика по аккаунтам"
        verbose_name_plural = "статистика по аккаунтам"
