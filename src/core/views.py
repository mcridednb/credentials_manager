from django.utils import timezone
from rest_framework import generics
from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny

from core.models import CredentialsProxy, CredentialsStatistics
from core.serializers import (
    CredentialsProxySerializer,
    CredentialsStatisticsSerializer,
)


class CredentialsProxyView(generics.RetrieveAPIView):
    serializer_class = CredentialsProxySerializer
    permission_classes = [AllowAny]

    def get_object(self):
        credentials_proxy = CredentialsProxy.objects.get_random(
            self.kwargs["network"]
        )

        if not credentials_proxy:
            raise NotFound(
                detail="Нет доступных аккаунтов, попробуйте повторить запрос позже",
                code=404,
            )

        credentials_proxy.status = CredentialsProxy.Status.SENT
        credentials_proxy.time_of_sent = timezone.now()
        credentials_proxy.counter += 1
        credentials_proxy.save()

        return credentials_proxy


class CredentialsProxyUpdateView(generics.UpdateAPIView):
    serializer_class = CredentialsProxySerializer
    permission_classes = [AllowAny]

    queryset = CredentialsProxy.objects.all()
    lookup_field = "pk"


class CredentialsStatisticsListView(generics.CreateAPIView):
    serializer_class = CredentialsStatisticsSerializer
    permission_classes = [AllowAny]

    queryset = CredentialsStatistics.objects.all()
