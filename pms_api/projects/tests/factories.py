"""
Factory Boy factories for projects app models.
"""

import factory
from factory.django import DjangoModelFactory

from pms_api.accounts.tests.factories import UserFactory
from pms_api.projects.models import Project
from pms_api.projects.models import ProjectStatus


class ProjectFactory(DjangoModelFactory):
    class Meta:
        model = Project

    code = factory.Sequence(lambda n: f"PRJ-{n:04d}")
    title = factory.Faker("sentence", nb_words=6)
    description = factory.Faker("paragraph")
    start_date = factory.Faker("date_this_year")
    total_budget = factory.Faker("pydecimal", left_digits=8, right_digits=2, positive=True)
    is_active = False
    created_by = factory.SubFactory(UserFactory)
    updated_by = factory.SubFactory(UserFactory)


class ProjectStatusFactory(DjangoModelFactory):
    class Meta:
        model = ProjectStatus

    project = factory.SubFactory(ProjectFactory)
    status = "registered"
    changed_by = factory.SubFactory(UserFactory)
    physical_progress_pct = factory.Faker(
        "pydecimal",
        left_digits=2,
        right_digits=2,
        positive=True,
        max_value=100,
    )
    financial_progress_pct = factory.Faker(
        "pydecimal",
        left_digits=2,
        right_digits=2,
        positive=True,
        max_value=100,
    )
    created_by = factory.SubFactory(UserFactory)
    updated_by = factory.SubFactory(UserFactory)
