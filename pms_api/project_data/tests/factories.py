"""
Factory Boy factories for project_data app models.
"""

import factory
from factory.django import DjangoModelFactory

from pms_api.accounts.tests.factories import UserFactory
from pms_api.project_data.models import Issue
from pms_api.project_data.models import IssueComment
from pms_api.project_data.models import Risk
from pms_api.projects.tests.factories import ProjectFactory


class IssueFactory(DjangoModelFactory):
    class Meta:
        model = Issue

    project = factory.SubFactory(ProjectFactory)
    title = factory.Faker("sentence", nb_words=6)
    description = factory.Faker("paragraph")
    severity = "medium"

    created_by = factory.SubFactory(UserFactory)
    updated_by = factory.SubFactory(UserFactory)


class IssueCommentFactory(DjangoModelFactory):
    class Meta:
        model = IssueComment

    issue = factory.SubFactory(IssueFactory)
    body = factory.Faker("sentence", nb_words=6)

    created_by = factory.SubFactory(UserFactory)
    updated_by = factory.SubFactory(UserFactory)


class RiskFactory(DjangoModelFactory):
    class Meta:
        model = Risk

    project = factory.SubFactory(ProjectFactory)
    title = factory.Faker("sentence")
    description = factory.Faker("paragraph")
    probability = "medium"
    impact = "medium"
    risk_owner = factory.SubFactory(UserFactory)

    created_by = factory.SubFactory(UserFactory)
    updated_by = factory.SubFactory(UserFactory)
