import django_filters

from core.models import Account


class AccountsFilter(django_filters.FilterSet):
    network = django_filters.CharFilter(
        field_name="network__title"
    )

    class Meta:
        model = Account
        fields = ["status", "network"]
