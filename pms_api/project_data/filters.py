import django_filters
from django.db.models import Case
from django.db.models import ExpressionWrapper
from django.db.models import IntegerField
from django.db.models import Value
from django.db.models import When

from pms_api.project_data.models import Risk


class RiskFilter(django_filters.FilterSet):
    min_score = django_filters.NumberFilter(
        method="filter_min_score",
    )

    class Meta:
        model = Risk
        fields = [
            "project",
            "probability",
            "impact",
            "risk_owner",
            "is_resolved",
        ]

    def filter_min_score(self, queryset, name, value):
        probability_score = Case(
            When(probability="low", then=Value(1)),
            When(probability="medium", then=Value(2)),
            When(probability="high", then=Value(3)),
            output_field=IntegerField(),
        )
        impact_score = Case(
            When(impact="low", then=Value(1)),
            When(impact="medium", then=Value(2)),
            When(impact="high", then=Value(3)),
            When(impact="critical", then=Value(4)),
            output_field=IntegerField(),
        )

        score = ExpressionWrapper(
            probability_score * impact_score,
            output_field=IntegerField(),
        )

        return queryset.annotate(
            score_value=score,
        ).filter(
            score_value__gte=value,
        )
