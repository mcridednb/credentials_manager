import json
import random

from django.utils import timezone
from loguru import logger
from rest_framework import serializers

from core.models import (
    Credentials,
    CredentialsProxy,
    CredentialsStatistics,
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
        fields = ["title", "types"]


class CredentialsSerializer(serializers.ModelSerializer):
    network = NetworkSerializer()

    class Meta:
        model = Credentials
        fields = ["network", "login", "password"]


class ProxySerializer(serializers.ModelSerializer):
    class Meta:
        model = Proxy
        fields = ["url", "mobile"]


class CredentialsProxySerializer(serializers.ModelSerializer):
    credentials = CredentialsSerializer()
    proxy = ProxySerializer()

    def to_internal_value(self, data):
        data = super().to_internal_value(data)

        if data.get("status") == CredentialsProxy.Status.USED:
            data["start_time_of_use"] = timezone.now()

        if data.get("status") == CredentialsProxy.Status.WAITING:
            if not data.get("waiting_delta"):
                data["waiting_delta"] = 60 * 60  # 1 hour

        if data.get("status") == CredentialsProxy.Status.TEMPORARILY_BANNED:
            if not data.get("waiting_delta"):
                data["waiting_delta"] = 60 * 60 * 2  # 2 hours

        cookies = data.get("cookies")
        if cookies is not None and isinstance(cookies, str):
            data['cookies'] = json.loads(cookies)

        logger.info(
            f"cred: {self.context['view'].kwargs['pk']}"
            f" - RECEIVE FROM MICROSERVICE "
            f"WITH STATUS '{data.get('status')}'"
        )

        return data

    def make_limits(self, types):
        return {type_['title']: type_['limit'] for type_ in types}

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if instance.credentials.network.dynamic_limits:
            parsing_types = data['credentials']['network']['types']
            for parsing_type in parsing_types:
                dynamic_limit = (instance.counter // 6) or 1
                if dynamic_limit <= parsing_type["limit"]:
                    parsing_type["limit"] = dynamic_limit
                parsing_type["limit"] = random.randint(
                    parsing_type["limit"]//2, parsing_type["limit"]
                )
            data['credentials']['network']['types'] = parsing_types
        data['limits'] = self.make_limits(
            data['credentials']['network']['types']
        )
        data['network'] = data['credentials']['network']['title']
        return data

    class Meta:
        model = CredentialsProxy
        fields = [
            "id",
            "status",
            "status_description",
            "credentials",
            "proxy",
            "start_time_of_use",
            "cookies",
        ]
        read_only_fields = ["id", "credentials", "proxy"]


class CredentialsStatisticsSerializer(serializers.ModelSerializer):
    def to_internal_value(self, data):
        data = super().to_internal_value(data)

        credentials_proxy = data['credentials_proxy']

        data["start_time_of_use"] = credentials_proxy.start_time_of_use
        data["end_time_of_use"] = timezone.now()

        return data

    class Meta:
        model = CredentialsStatistics
        fields = [
            "id",
            "credentials_proxy",
            "account_title",
            "start_time_of_use",
            "end_time_of_use",
            "request_count",
            "limit",
            "result_status",
            "status_description",
        ]
        read_only_fields = ["id"]
        extra_kwargs = {
            "start_time_of_use": {"required": False, "allow_null": True},
            "end_time_of_use": {"required": False, "allow_null": True}
        }
