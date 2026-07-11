import pytest

from pms_api.core.models.notifications import Notification
from pms_api.project_data.tests.factories import RiskFactory
from pms_api.projects.tests.factories import ProjectFactory


@pytest.mark.django_db
class TestRiskNotifications:
    def test_high_risk_creates_notification(
        self,
        project_type,
        location,
        department,
    ):
        project = ProjectFactory(
            project_type=project_type,
            location=location,
            implementing_department=department,
        )

        risk = RiskFactory(
            project=project,
            impact="high",
        )

        assert Notification.objects.count() == 1

        notification = Notification.objects.first()

        assert notification.recipient == risk.risk_owner
        assert notification.content_object == risk
        assert notification.actor == risk.created_by
        assert notification.verb == f"High-risk '{risk.title}' has been assigned to you."

    def test_low_risk_does_not_create_notification(
        self,
        project_type,
        location,
        department,
    ):
        project = ProjectFactory(
            project_type=project_type,
            location=location,
            implementing_department=department,
        )

        RiskFactory(
            project=project,
            impact="low",
        )

        assert Notification.objects.count() == 0

    def test_updating_risk_does_not_create_duplicate_notification(
        self,
        project_type,
        location,
        department,
    ):
        project = ProjectFactory(
            project_type=project_type,
            location=location,
            implementing_department=department,
        )

        risk = RiskFactory(
            project=project,
            impact="high",
        )

        assert Notification.objects.count() == 1

        risk.title = "Updated title"
        risk.save()

        assert Notification.objects.count() == 1
