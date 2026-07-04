"""
Tests for Risk Heatmap API.
"""

import pytest
from django.urls import reverse
from rest_framework import status

from pms_api.project_data.tests.factories import RiskFactory
from pms_api.projects.tests.factories import ProjectFactory


@pytest.mark.django_db
class TestRiskAPI:
    def test_risk_serializer_includes_score(
        self,
        admin_client,
        project_type,
        location,
        department,
        superuser,
    ):
        project = ProjectFactory(
            project_type=project_type,
            location=location,
            implementing_department=department,
        )
        risk = RiskFactory(
            project=project,
            probability="high",
            impact="critical",
            risk_owner=superuser,
        )
        url = reverse(
            "api:project_data:risk-detail",
            kwargs={"uuid": risk.uuid},
        )

        response = admin_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["score"] == 12

    def test_filter_risks_by_min_score(
        self,
        admin_client,
        project_type,
        location,
        department,
        superuser,
    ):
        project = ProjectFactory(
            project_type=project_type,
            location=location,
            implementing_department=department,
        )
        RiskFactory(
            project=project,
            probability="low",
            impact="low",
            risk_owner=superuser,
        )

        RiskFactory(
            project=project,
            probability="medium",
            impact="high",
            risk_owner=superuser,
        )

        RiskFactory(
            project=project,
            probability="high",
            impact="critical",
            risk_owner=superuser,
        )

        url = reverse("api:project_data:risk-list")

        response = admin_client.get(
            url,
            {"min_score": 6},
        )
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["data"]) == 2
        scores = {risk["score"] for risk in response.data["data"]}

        assert scores == {6, 12}

    def test_heatmap(
        self,
        admin_client,
        project_type,
        location,
        department,
        superuser,
    ):
        project = ProjectFactory(
            project_type=project_type,
            location=location,
            implementing_department=department,
        )
        RiskFactory(
            project=project,
            probability="high",
            impact="critical",
            risk_owner=superuser,
        )
        RiskFactory(
            project=project,
            probability="high",
            impact="critical",
            risk_owner=superuser,
        )
        RiskFactory(
            project=project,
            probability="medium",
            impact="high",
            risk_owner=superuser,
        )

        url = reverse("api:project_data:risk-heatmap")
        response = admin_client.get(url)

        assert response.status_code == status.HTTP_200_OK

        heatmap = response.data["data"]

        assert heatmap["high"]["critical"] == 2
        assert heatmap["medium"]["high"] == 1
        assert heatmap["low"]["low"] == 0
