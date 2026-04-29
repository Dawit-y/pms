"""
Factory Boy factories for budget app models.
"""

import factory
from factory.django import DjangoModelFactory

from pms_api.accounts.tests.factories import UserFactory
from pms_api.budget.models import BudgetForwardingStep
from pms_api.budget.models import BudgetRequest


class BudgetRequestFactory(DjangoModelFactory):
    class Meta:
        model = BudgetRequest

    requested_amount = factory.Faker("pydecimal", left_digits=8, right_digits=2, positive=True)
    fiscal_year = factory.Faker("year")
    justification = factory.Faker("paragraph")
    status = "draft"
    created_by = factory.SubFactory(UserFactory)
    updated_by = factory.SubFactory(UserFactory)


class BudgetForwardingStepFactory(DjangoModelFactory):
    class Meta:
        model = BudgetForwardingStep

    budget_request = factory.SubFactory(BudgetRequestFactory)
    action = "forwarded"
    acted_by = factory.SubFactory(UserFactory)
    step_number = 1
    created_by = factory.SubFactory(UserFactory)
    updated_by = factory.SubFactory(UserFactory)
