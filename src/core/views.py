from django_filters import rest_framework as filters
from loguru import logger
from rest_framework import generics
from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from core import amqp, tasks
from core.filters import CredentialsFilter
from core.models import CredentialsProxy, CredentialsStatistics, ParsingType
from core.serializers import (
    CredentialsProxySerializer,
    CredentialsStatisticsSerializer, ParsingTypeSerializer,
)


class CredentialsProxyView(generics.RetrieveAPIView):
    serializer_class = CredentialsProxySerializer
    permission_classes = [AllowAny]

    def retrieve(self, request, *args, **kwargs):
        credentials_proxy = amqp.consume(self.kwargs["network"])

        if not credentials_proxy:
            raise NotFound(
                detail="Нет доступных аккаунтов, попробуйте повторить запрос позже",
                code=404,
            )

        if isinstance(credentials_proxy, list):
            for credentials in credentials_proxy:
                logger.info(f"cred: {credentials['id']} - RECEIVE FROM QUEUE")
                tasks.update_account_status.delay(
                    credentials["id"], CredentialsProxy.Status.SENT
                )
            credentials_proxy = {"accounts": credentials_proxy}
        else:
            logger.info(f"cred: {credentials_proxy['id']} - RECEIVE FROM QUEUE")
            tasks.update_account_status.delay(
                credentials_proxy["id"], CredentialsProxy.Status.SENT
            )

        return Response(credentials_proxy)


class CredentialsProxyUpdateView(generics.UpdateAPIView):
    serializer_class = CredentialsProxySerializer
    permission_classes = [AllowAny]

    queryset = CredentialsProxy.objects.all()
    lookup_field = "pk"


class CredentialsProxyListView(generics.ListAPIView):
    serializer_class = CredentialsProxySerializer
    permission_classes = [AllowAny]

    filter_backends = [filters.DjangoFilterBackend]
    filterset_class = CredentialsFilter


class CredentialsStatisticsListView(generics.CreateAPIView):
    serializer_class = CredentialsStatisticsSerializer
    permission_classes = [AllowAny]

    queryset = CredentialsStatistics.objects.all()


class LimitsView(generics.ListAPIView):
    serializer_class = ParsingTypeSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        return ParsingType.objects.filter(network__title=self.kwargs["network"])
