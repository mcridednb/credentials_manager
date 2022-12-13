import csv
from datetime import datetime
import io
import json

from django.contrib import admin, messages
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import path
from django.utils import timezone

from core import pydantic_models as pmodels, tasks
from core.forms import CsvImportForm
from core.models import (Account, AccountStatistics, Network, ParsingType, Proxy, ProxyRent)


def get_date(date):
    if not date:
        return
    return datetime.strptime(date, "%d.%m.%Y")


class ReadOnlyMixin:
    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class AccountStatisticsInline(ReadOnlyMixin, admin.TabularInline):
    model = AccountStatistics


class ProxyRentInline(ReadOnlyMixin, admin.TabularInline):
    model = ProxyRent


def create_proxy(proxy: pmodels.Proxy):
    proxy_obj, created = Proxy.objects.update_or_create(
        type=proxy.type,
        ip=proxy.ip,
        port=proxy.port,
        defaults={
            "login": proxy.login,
            "password": proxy.password,
            "mobile": proxy.mobile,
            "market": proxy.market,
            "status": Proxy.Status.AVAILABLE,
            "enable": True,
        }
    )
    ProxyRent.objects.get_or_create(
        proxy=proxy_obj,
        expiration_date=proxy.expiration_date,
        defaults={
            "price": proxy.price
        }
    )
    return proxy_obj


@admin.register(Proxy)
class ProxyAdmin(admin.ModelAdmin):
    change_list_template = "entities/proxy_changelist.html"

    list_display = (
        "__str__",
        "status",
        "status_updated",
        "mobile",
        "market",
        "enable",
    )
    list_editable = (
        "mobile",
        "enable",
    )

    search_fields = ["ip"]
    list_filter = ["status", "market", "rents__expiration_date"]

    actions = ["export_as_csv"]

    inlines = [ProxyRentInline]

    def get_urls(self):
        urls = super().get_urls()
        return [
            path("update-statuses/", self.update_statuses),
            path("import-csv/", self.import_csv),
            *urls,
        ]

    def import_csv(self, request):
        if request.method != "POST":
            return render(
                request, "admin/csv_form.html", {"form": CsvImportForm()}
            )

        reader = csv.DictReader(
            io.StringIO(request.FILES["csv_file"].read().decode("utf-8"))
        )

        for proxy in reader:
            try:
                proxy = pmodels.Proxy.parse_obj(proxy)
            except Exception as e:
                self.message_user(
                    request,
                    f"Ошибка валидации файла: {e}",
                    level=messages.ERROR,
                )
                return redirect("..")

            create_proxy(proxy)

        self.message_user(request, "Прокси были успешно добавлены")
        return redirect("..")

    @admin.action(description="Выгрузить в csv")
    def export_as_csv(self, request, queryset):
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = f"attachment; filename=proxy_{queryset.count()}.csv"
        writer = csv.writer(response)

        writer.writerow([
            "login",
            "password",
            "ip",
            "port",
            "type",
            "mobile",
            "market",
            "expiration_date",
            "price",
        ])
        for obj in queryset:
            last_rent = obj.rents.last()
            date = None
            price = None
            if last_rent:
                date = last_rent.expiration_date.strftime("%d.%m.%Y")
                price = last_rent.price

            writer.writerow([
                obj.login,
                obj.password,
                obj.ip,
                obj.port,
                obj.type,
                str(obj.mobile).lower(),
                obj.market,
                date,
                price,
            ])

        return response

    def update_statuses(self, request):
        tasks.update_proxy_statuses.delay()

        self.message_user(
            request, "Задача на обновление статусов была поставлена"
        )

        return redirect("..")


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    change_list_template = "entities/accounts_changelist.html"

    list_display = (
        "proxy",
        "status",
        "status_updated",
        "waiting_delta",
        "start_time_of_use",
        "enable",
    )

    list_editable = ("enable", "status")

    raw_id_fields = ["proxy"]
    readonly_fields = [
        "time_of_sent",
        "status_description",
        "status_updated",
        "waiting_delta",
        "start_time_of_use",
        "cookies",
    ]

    search_fields = ["login", "proxy__ip", "token"]
    list_filter = ["network", "status"]

    inlines = [AccountStatisticsInline]

    actions = ["make_available", "export_as_csv"]

    @admin.action(description="Поменять статус на «Available»")
    def make_available(self, request, queryset):
        updated = queryset.update(
            status=Account.Status.AVAILABLE,
            status_updated=timezone.now(),
        )
        self.message_user(request, f"{updated} аккаунтов были изменены")

    def get_urls(self):
        urls = super().get_urls()
        return [
            path("load-to-queue/", self.load_to_queue),
            path("import-csv/", self.import_csv),
            *urls,
        ]

    def load_to_queue(self, request):
        tasks.load_accounts_to_queue.delay()

        self.message_user(
            request, "Задача на добавление аккаунтов в очередь была поставлена"
        )

        return redirect("..")

    def import_csv(self, request):
        if request.method != "POST":
            return render(
                request, "admin/csv_form.html", {"form": CsvImportForm()}
            )

        reader = csv.DictReader(
            io.StringIO(request.FILES["csv_file"].read().decode("utf-8"))
        )

        for account in reader:
            try:
                account = pmodels.Account.parse_obj(account)
            except Exception as e:
                self.message_user(
                    request,
                    f"Ошибка валидации файла: {e}",
                    level=messages.ERROR,
                )
                return redirect("..")

            proxy = None
            if account.proxy:
                proxy = create_proxy(account.proxy)

            try:
                network = Network.objects.get(title=account.network)
            except Network.DoesNotExist:
                self.message_user(
                    request,
                    f"Сеть с названием {account.network} не найдена",
                    level=messages.ERROR,
                )
                return redirect("..")

            Account.objects.update_or_create(
                network=network,
                login=account.login,
                token=account.token,
                cookies=account.cookies,
                defaults={
                    "password": account.password,
                    "proxy": proxy,
                    "price": account.price,
                    "market": account.market,
                    "status": Account.Status.AVAILABLE,
                    "status_description": "Updated from file",
                    "enable": True,
                }
            )

        self.message_user(request, "Прокси-аккаунты были успешно добавлены")
        return redirect("..")

    @admin.action(description="Выгрузить в csv")
    def export_as_csv(self, request, queryset):
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = f"attachment; filename=accounts_{queryset.count()}.csv"
        writer = csv.writer(response)

        writer.writerow([
            "network",
            "login",
            "password",
            "price",
            "market",
            "token",
            "cookies",
            "proxy_login",
            "proxy_password",
            "proxy_ip",
            "proxy_port",
            "proxy_type",
            "proxy_mobile",
            "proxy_market",
            "proxy_expiration_date",
            "proxy_price",
        ])
        for obj in queryset:
            proxy_part = []
            if obj.proxy:
                last_rent = obj.proxy.rents.last()
                date = None
                price = None
                if last_rent:
                    date = last_rent.expiration_date.strftime("%d.%m.%Y")
                    price = last_rent.price
                proxy_part = [
                    obj.proxy.login,
                    obj.proxy.password,
                    obj.proxy.ip,
                    obj.proxy.port,
                    obj.proxy.type,
                    obj.proxy.mobile,
                    obj.proxy.market,
                    date,
                    price,
                ]

            writer.writerow([
                obj.network.title,
                obj.login,
                obj.password,
                obj.price,
                obj.market,
                obj.token,
                json.dumps(obj.cookies),
                *proxy_part,
            ])

        return response


@admin.register(AccountStatistics)
class AccountStatisticsAdmin(ReadOnlyMixin, admin.ModelAdmin):
    list_display = (
        "account__id",
        "start_time_of_use",
        "end_time_of_use",
        "request_count",
        "limit",
        "result_status",
        "proxy__id",
    )


class ParsingTypeInline(admin.TabularInline):
    model = ParsingType


@admin.register(Network)
class NetworkAdmin(admin.ModelAdmin):
    inlines = [ParsingTypeInline]
