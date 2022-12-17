import json
import random

from django.utils import timezone
from loguru import logger
from rest_framework import serializers

from core.models import (
    Account,
    AccountStatistics,
    Proxy,
    Network,
    ParsingType,
)


class ParsingTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ParsingType
        fields = ["title", "code", "limit"]


class NetworkSerializer(serializers.ModelSerializer):
    types = ParsingTypeSerializer(many=True)

    class Meta:
        model = Network
        fields = ["title", "dynamic_limits", "types"]


class ProxySerializer(serializers.ModelSerializer):
    related_accounts_count = serializers.IntegerField(
        required=False, default=None
    )

    class Meta:
        model = Proxy
        fields = [
            "id", "url", "mobile", "enable", "status", "related_accounts_count"
        ]


class AccountSerializer(serializers.ModelSerializer):
    network = NetworkSerializer()

    def to_internal_value(self, data):
        data = super().to_internal_value(data)

        if data.get("status") == Account.Status.WAITING:
            if not data.get("waiting_delta"):
                data["waiting_delta"] = 60 * 60  # 1 hour

        if data.get("status") == Account.Status.TEMPORARILY_BANNED:
            if not data.get("waiting_delta"):
                data["waiting_delta"] = 60 * 60 * 2  # 2 hours

        cookies = data.get("cookies")
        if cookies is not None and isinstance(cookies, str):
            data["cookies"] = json.loads(cookies)

        data["enable"] = data.get("status") in [
            Account.Status.AVAILABLE,
            Account.Status.WAITING,
            Account.Status.TEMPORARILY_BANNED,
        ]

        logger.info(
            f"account: {self.context['view'].kwargs['pk']}"
            f" - RECEIVE FROM MICROSERVICE "
            f"WITH STATUS '{data.get('status')}'"
        )

        return data

    @staticmethod
    def make_limits(types):
        return {type_["title"]: type_["limit"] for type_ in types}

    @staticmethod
    def calculate_limits(parsing_types, counter):
        for parsing_type in parsing_types:
            dynamic_limit = (counter // 6) or 1

            if dynamic_limit <= parsing_type["limit"]:
                parsing_type["limit"] = dynamic_limit

            parsing_type["limit"] = random.randint(
                parsing_type["limit"] // 2, parsing_type["limit"]
            )
        return parsing_types

    def to_representation(self, instance):
        data = super().to_representation(instance)

        if instance.network.dynamic_limits:
            data["network"]["types"] = self.calculate_limits(
                data["network"]["types"], instance.counter
            )

        data["limits"] = self.make_limits(data["network"]["types"])
        data["network"] = data["network"]["title"]

        if not instance.proxy and instance.network.need_proxy:
            raise ValueError("Account not ready")

        if instance.proxy:
            data["proxy"] = ProxySerializer(instance.proxy).data
        return data

    class Meta:
        model = Account
        fields = [
            "id",
            "network",
            "login",
            "password",
            "proxy",
            "cookies",
            "token",
            "enable",

            "status",
            "status_description",
        ]
        read_only_fields = ["id", "proxy", "network", "login", "password"]
        extra_kwargs = {
            "status": {"write_only": True},
            "status_description": {"write_only": True},
            "enable": {"write_only": True},
        }


class AccountStatisticsSerializer(serializers.ModelSerializer):
    def to_internal_value(self, data):
        data = super().to_internal_value(data)

        account = data["account"]

        data["account_title"] = str(account)
        data["start_time_of_use"] = account.start_time_of_use
        data["end_time_of_use"] = timezone.now()
        data["proxy"] = account.proxy

        return data

    class Meta:
        model = AccountStatistics
        fields = [
            "id",
            "account",
            "start_time_of_use",
            "end_time_of_use",
            "request_count",
            "limit",
            "result_status",
            "status_description",
            "proxy",
        ]
        read_only_fields = ["id"]
        extra_kwargs = {
            "start_time_of_use": {"required": False, "allow_null": True},
            "end_time_of_use": {"required": False, "allow_null": True}
        }
