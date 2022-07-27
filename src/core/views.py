from rest_framework import generics
from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from core import amqp, tasks
from core.models import CredentialsProxy, CredentialsStatistics
from core.serializers import (
    CredentialsProxySerializer,
    CredentialsStatisticsSerializer,
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

        tasks.update_account_status.delay(
            credentials_proxy["id"], CredentialsProxy.Status.SENT
        )
        return Response(credentials_proxy)


class CredentialsProxyUpdateView(generics.UpdateAPIView):
    serializer_class = CredentialsProxySerializer
    permission_classes = [AllowAny]

    queryset = CredentialsProxy.objects.all()
    lookup_field = "pk"


class CredentialsStatisticsListView(generics.CreateAPIView):
    serializer_class = CredentialsStatisticsSerializer
    permission_classes = [AllowAny]

    queryset = CredentialsStatistics.objects.all()
