import csv
import io

from django.contrib import admin
from django.db import IntegrityError
from django.shortcuts import redirect, render
from django.urls import path

from core.forms import CsvImportForm
from core.models import (
    Credentials,
    CredentialsProxy,
    Network,
    Proxy,
    CredentialsStatistics,
    ParsingType,
)
from core.tasks import generate_credentials_proxy, update_proxy_statuses


class ReadOnlyMixin:
    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class CredentialsStatisticsInline(ReadOnlyMixin, admin.TabularInline):
    model = CredentialsStatistics


@admin.register(Credentials)
class CredentialsAdmin(admin.ModelAdmin):
    change_list_template = "entities/credentials_changelist.html"

    list_display = ('__str__', 'enable')
    list_editable = ('enable',)

    def get_urls(self):
        urls = super().get_urls()
        return [
            path('import-csv/', self.import_csv),
            *urls,
        ]

    def import_csv(self, request):
        if request.method == "POST":
            reader = csv.DictReader(
                io.StringIO(request.FILES["csv_file"].read().decode("utf-8"))
            )

            for credentials in reader:
                try:
                    network, _ = Network.objects.get_or_create(
                        title=credentials.pop("network"),
                        defaults={"limit": 50}
                    )
                    login = credentials.pop("login")
                    credentials, created = Credentials.objects.update_or_create(
                        network=network, login=login, defaults=credentials
                    )
                    if not created:
                        credentials.credentialsproxy.status = (
                            CredentialsProxy.Status.AVAILABLE
                        )
                        credentials.credentialsproxy.save()
                except IntegrityError:
                    pass

            self.message_user(request, "Аккаунты были успешно добавлены")
            return redirect("..")

        form = CsvImportForm()

        return render(
            request, "admin/csv_form.html", {"form": form}
        )


@admin.register(Proxy)
class ProxyAdmin(admin.ModelAdmin):
    change_list_template = "entities/proxy_changelist.html"

    list_display = (
        '__str__',
        'status',
        'status_updated',
        'enable'
    )
    list_editable = ('enable',)

    def get_urls(self):
        urls = super().get_urls()
        return [
            path('update-statuses/', self.update_statuses),
            path('import-csv/', self.import_csv),
            *urls,
        ]

    def import_csv(self, request):
        if request.method == "POST":
            reader = csv.DictReader(
                io.StringIO(request.FILES["csv_file"].read().decode("utf-8"))
            )

            for proxy in reader:
                try:
                    ip, port = proxy.pop("ip"), proxy.pop("port")
                    Proxy.objects.update_or_create(
                        ip=ip, port=port, defaults=proxy
                    )
                except IntegrityError:
                    pass

            self.message_user(request, "Прокси были успешно добавлены")
            return redirect("..")

        form = CsvImportForm()

        return render(
            request, "admin/csv_form.html", {"form": form}
        )

    def update_statuses(self, request):
        update_proxy_statuses.delay()

        self.message_user(
            request, "Задача на обновление статусов была поставлена"
        )

        return redirect("..")


@admin.register(CredentialsProxy)
class CredentialsProxyAdmin(admin.ModelAdmin):
    change_list_template = "entities/credentials_proxy_changelist.html"

    list_display = (
        'credentials',
        'proxy',
        'status',
        'status_updated',
        'waiting_delta',
        'start_time_of_use',
        'enable',
    )

    list_editable = ('enable', 'status')

    readonly_fields = [
        'time_of_sent',
        'status_description',
        'status_updated',
        'waiting_delta',
        'start_time_of_use',
        'cookies'
    ]

    inlines = [CredentialsStatisticsInline]

    def get_urls(self):
        urls = super().get_urls()
        return [
            path('generate/', self.generate),
            # path('update-statuses/', self.update_statuses),
            path('import-csv/', self.import_csv),
            *urls,
        ]

    def generate(self, request):
        generate_credentials_proxy.delay()

        self.message_user(
            request, "Задача на генерацию прокси-аккаунтов была поставлена"
        )

        return redirect("..")

    def import_csv(self, request):
        if request.method == "POST":
            reader = csv.DictReader(
                io.StringIO(request.FILES["csv_file"].read().decode("utf-8"))
            )

            for credentials_proxy in reader:
                try:
                    ip, port = credentials_proxy.pop("ip"), credentials_proxy.pop("port")
                    proxy, _ = Proxy.objects.update_or_create(
                        ip=ip, port=port, defaults={
                            "login": credentials_proxy.pop("proxy_login"),
                            "password": credentials_proxy.pop("proxy_password"),
                            "enable": True,
                            "status": Proxy.Status.AVAILABLE,
                        }
                    )
                except IntegrityError:
                    pass
                else:
                    try:
                        network, _ = Network.objects.get_or_create(
                            title=credentials_proxy.pop("network"),
                            defaults={"limit": 50}
                        )
                        login = credentials_proxy.pop("login")
                        credentials, created = Credentials.objects.update_or_create(
                            network=network, login=login, defaults={
                                "password": credentials_proxy.pop("password"),
                                "enable": True,
                            }
                        )
                        CredentialsProxy.objects.update_or_create(
                            credentials=credentials,
                            proxy=proxy,
                            defaults={
                                "status": CredentialsProxy.Status.AVAILABLE,
                                "enable": True,
                            }
                        )
                    except IntegrityError:
                        pass

            self.message_user(request, "Прокси-аккаунты были успешно добавлены")
            return redirect("..")

        form = CsvImportForm()

        return render(
            request, "admin/csv_form.html", {"form": form}
        )


@admin.register(CredentialsStatistics)
class CredentialsStatisticsAdmin(ReadOnlyMixin, admin.ModelAdmin):
    list_display = (
        'account_title',
        'start_time_of_use',
        'end_time_of_use',
        'request_count',
        'limit',
        'result_status',
    )


class ParsingTypeInline(admin.TabularInline):
    model = ParsingType


@admin.register(Network)
class NetworkAdmin(admin.ModelAdmin):
    inlines = [ParsingTypeInline]
