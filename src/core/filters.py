import django_filters

from core.models import CredentialsProxy


class CredentialsFilter(django_filters.FilterSet):
    network = django_filters.CharFilter(
        lookup_expr="credentials__network__title"
    )

    class Meta:
        model = CredentialsProxy
        fields = ["status", "network"]
