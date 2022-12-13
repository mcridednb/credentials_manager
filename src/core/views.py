from django.db.models import Count, Q
from django_filters import rest_framework as filters
from loguru import logger
from rest_framework import generics
from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from core import amqp, tasks
from core.filters import AccountsFilter
from core.models import Account, AccountStatistics, ParsingType, Proxy
from core.serializers import (
    AccountSerializer,
    AccountStatisticsSerializer,
    ParsingTypeSerializer,
    ProxySerializer,
)
from core.utils import get_client_ip


class AccountView(generics.RetrieveAPIView):
    serializer_class = AccountSerializer
    permission_classes = [AllowAny]

    def retrieve(self, request, *args, **kwargs):
        logger.info(
            f"ip: {get_client_ip(request)} - "
            f"RECEIVE REQUEST FOR {self.kwargs['network'].upper()}"
        )

        account = amqp.consume(self.kwargs["network"])

        if not account:
            raise NotFound(
                detail="Нет доступных аккаунтов, попробуйте повторить запрос позже",
                code=404,
            )

        if isinstance(account, list):
            for row in account:
                logger.info(f"account: {row['id']} - RECEIVE FROM QUEUE")
                tasks.update_account_status.delay(
                    row["id"], Account.Status.SENT
                )
            account = {"accounts": account}
        else:
            logger.info(f"account: {account['id']} - RECEIVE FROM QUEUE")
            tasks.update_account_status.delay(
                account["id"], Account.Status.SENT
            )

        return Response(account)


class AccountUpdateView(generics.UpdateAPIView):
    serializer_class = AccountSerializer
    permission_classes = [AllowAny]

    queryset = Account.objects.all()
    lookup_field = "pk"


class AccountListView(generics.ListAPIView):
    queryset = Account.objects.all()

    serializer_class = AccountSerializer
    permission_classes = [AllowAny]

    filter_backends = [filters.DjangoFilterBackend]
    filterset_class = AccountsFilter


class ProxyListView(generics.ListAPIView):
    serializer_class = ProxySerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        return Proxy.objects.filter(
            enable=True, status=Proxy.Status.AVAILABLE
        ).annotate(
            related_accounts_count=Count("accounts")
        ).order_by("related_accounts_count")


class ProxyView(generics.RetrieveAPIView):
    serializer_class = ProxySerializer
    permission_classes = [AllowAny]

    def retrieve(self, request, *args, **kwargs):
        obj = Proxy.objects.filter(
            enable=True, status=Proxy.Status.AVAILABLE
        ).annotate(
            related_accounts_count=Count(
                "accounts", filter=Q(
                    accounts__network__title=self.kwargs['network']
                )
            )
        ).order_by("related_accounts_count").first()

        return Response(self.serializer_class(obj).data)


class AccountStatisticsListView(generics.CreateAPIView):
    serializer_class = AccountStatisticsSerializer
    permission_classes = [AllowAny]

    queryset = AccountStatistics.objects.all()


class LimitsView(generics.ListAPIView):
    serializer_class = ParsingTypeSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        return ParsingType.objects.filter(network__title=self.kwargs["network"])
