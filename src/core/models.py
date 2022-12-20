from datetime import datetime, timedelta
import logging

from django.db import models
from django.db.models import Count, Q

from core.utils import check_proxy, send_telegram_notification

logger = logging.getLogger(__name__)


class Network(models.Model):
    title = models.CharField(max_length=255, unique=True)
    dynamic_limits = models.BooleanField(default=False)
    need_proxy = models.BooleanField(default=False)

    def __str__(self):
        return self.title

    class Meta:
        verbose_name = "сеть"
        verbose_name_plural = "сети"


class Proxy(models.Model):
    class Type(models.TextChoices):
        SOCKS5 = "socks5"
        HTTP = "http"
        HTTPS = "https"

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

    mobile = models.BooleanField(default=False)

    market = models.CharField(
        max_length=255, default="unknown", null=True, blank=True
    )

    status = models.CharField(
        max_length=255, choices=Status.choices, default=Status.AVAILABLE
    )
    status_updated = models.DateTimeField(auto_now=True)

    enable = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.ip}:{self.port}"

    @property
    def url(self):
        if self.type == self.Type.SOCKS5:
            self.type = self.type + "h"
        return f"{self.type}://{self.login}:{self.password}@{self.ip}:{self.port}"

    def check_expiration(self):
        last_rent = self.rents.last()
        if last_rent:
            last_rent.check_expiration()

    def update_status(self):
        try:
            result_ip = check_proxy(self.url)
        except Exception as e:
            self.status = self.Status.NOT_AVAILABLE
            self.enable = False

            send_telegram_notification(f"Закончились прокси: {self.ip}")

            logger.warning(f"Something went wrong with ip: {self.ip}: {e}")
        else:
            self.enable = True
            if self.ip == result_ip:
                self.status = self.Status.AVAILABLE
            else:
                if self.mobile:
                    self.status = self.Status.AVAILABLE
                else:
                    self.status = self.Status.IP_NOT_EQUAL
            self.check_expiration()
        finally:
            self.save()

    @classmethod
    def get_first_for(cls, network: str):
        return cls.objects.filter(
            enable=True, status=Proxy.Status.AVAILABLE
        ).annotate(
            related_accounts_count=Count(
                "accounts", filter=Q(
                    accounts__network__title=network,
                    accounts__enable=True,
                )
            )
        ).order_by("related_accounts_count").first()

    class Meta:
        verbose_name = "прокси"
        verbose_name_plural = "прокси"
        constraints = [
            models.UniqueConstraint(
                fields=["ip", "port"], name="ip_port_constraint"
            )
        ]


class ProxyRent(models.Model):
    proxy = models.ForeignKey(
        Proxy, related_name="rents", on_delete=models.PROTECT
    )
    expiration_date = models.DateField(null=True, blank=True)
    price = models.IntegerField(null=True, blank=True)

    five_day_notification = models.BooleanField(default=False)
    tomorrow_notification = models.BooleanField(default=False)
    today_notification = models.BooleanField(default=False)

    def check_expiration(self):
        if self.expiration_date == (datetime.today() + timedelta(days=5)).date():
            if not self.five_day_notification:
                send_telegram_notification(
                    f"Через 5 дней заканчиваются прокси {self.proxy.ip}"
                )
                self.five_day_notification = True

        if self.expiration_date == (datetime.today() + timedelta(days=1)).date():
            if not self.tomorrow_notification:
                send_telegram_notification(
                    f"Завтра заканчиваются прокси {self.proxy.ip}"
                )
                self.tomorrow_notification = True

        if self.expiration_date == datetime.today().date():
            if not self.today_notification:
                send_telegram_notification(
                    f"Сегодня заканчиваются прокси {self.proxy.ip}"
                )
                self.today_notification = True

    class Meta:
        verbose_name = "аренда прокси"
        verbose_name_plural = "аренда прокси"


class ProxyCounter(models.Model):
    network = models.ForeignKey(Network, on_delete=models.PROTECT)
    proxy = models.ForeignKey(
        Proxy, related_name="counters", on_delete=models.PROTECT
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


class Account(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = "available"
        IN_QUEUE = "in_queue"
        SENT = "sent"
        INVALID = "invalid"
        NOT_AVAILABLE = "not_available"
        PROXY_ERROR = "proxy_error"
        LOGIN_FAILED = "login_failed"
        TEMPORARILY_BANNED = "temporarily_banned"
        BANNED = "banned"
        WAITING = "waiting"

    network = models.ForeignKey(Network, on_delete=models.PROTECT, null=True)

    login = models.CharField(max_length=255, null=True, blank=True)
    password = models.CharField(max_length=255, null=True, blank=True)

    proxy = models.ForeignKey(
        Proxy,
        on_delete=models.SET_NULL,
        related_name="accounts",
        null=True,
        blank=True,
    )

    price = models.IntegerField(null=True, blank=True)
    market = models.CharField(
        max_length=255, default="unknown", null=True, blank=True
    )

    status = models.CharField(
        max_length=255, choices=Status.choices, default=Status.AVAILABLE
    )
    status_description = models.CharField(max_length=1024, null=True, blank=True)
    status_updated = models.DateTimeField(auto_now=True)

    waiting_delta = models.IntegerField(default=60 * 60, help_text="In seconds")

    time_of_sent = models.DateTimeField(null=True, blank=True)
    token = models.CharField(max_length=255, null=True, blank=True)

    cookies = models.JSONField(null=True, blank=True)

    counter = models.IntegerField(default=0)

    enable = models.BooleanField(default=True)

    def __str__(self):
        _id = self.login or self.token[:10] or self.id
        return f"{self.network}:{_id}"

    class Meta:
        verbose_name = "аккаунт"
        verbose_name_plural = "аккаунты"
        constraints = [
            models.UniqueConstraint(
                fields=["network", "login"], name="network_login_constraint"
            )
        ]


class AccountStatistics(models.Model):
    class Status(models.TextChoices):
        NOT_AVAILABLE = 'not_available'
        LOGIN_FAILED = 'login_failed'
        TEMPORARILY_BANNED = 'temporarily_banned'
        BANNED = 'banned'
        WAITING = 'waiting'

    account = models.ForeignKey(
        Account, on_delete=models.CASCADE, related_name="statistics"
    )
    time_of_sent = models.DateTimeField()
    end_time_of_use = models.DateTimeField()

    request_count = models.JSONField(null=True)
    limits = models.JSONField(null=True)

    result_status = models.CharField(max_length=255, choices=Status.choices)
    status_description = models.TextField(null=True, blank=True)

    proxy = models.ForeignKey(
        Proxy,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="statistics"
    )

    def __str__(self):
        return str(self.id)

    class Meta:
        verbose_name = "статистика по аккаунтам"
        verbose_name_plural = "статистика по аккаунтам"


class ParsingType(models.Model):
    network = models.ForeignKey(
        Network, on_delete=models.CASCADE, related_name='types'
    )
    title = models.CharField(max_length=255)
    code = models.CharField(max_length=255, null=True)
    limit = models.IntegerField(default=0)

    class Meta:
        verbose_name = "Типы парсинга"
        verbose_name_plural = "Типы парсинга"
