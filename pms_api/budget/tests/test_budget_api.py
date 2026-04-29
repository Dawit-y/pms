"""
Tests for Budget API endpoints.
"""

import pytest
from django.urls import reverse
from rest_framework import status

from pms_api.budget.models import BudgetRequest
from pms_api.budget.tests.factories import BudgetRequestFactory
from pms_api.projects.tests.factories import ProjectFactory


@pytest.mark.django_db
class TestBudgetRequestAPI:
    def test_list_budget_requests(self, admin_client, project_type, location, department):
        """Test listing budget requests."""
        # Create separate projects for each budget request (one-to-one relationship)
        project1 = ProjectFactory(
            project_type=project_type,
            location=location,
            implementing_department=department,
        )
        project2 = ProjectFactory(
            project_type=project_type,
            location=location,
            implementing_department=department,
        )
        project3 = ProjectFactory(
            project_type=project_type,
            location=location,
            implementing_department=department,
        )
        BudgetRequestFactory(project=project1)
        BudgetRequestFactory(project=project2)
        BudgetRequestFactory(project=project3)
        url = reverse("api:budget:budget-request-list")
        response = admin_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["data"]) >= 3

    def test_create_budget_request(self, admin_client, project_type, location, department):
        """Test creating a budget request."""
        project = ProjectFactory(
            project_type=project_type,
            location=location,
            implementing_department=department,
        )
        url = reverse("api:budget:budget-request-list")
        data = {
            "project": project.id,
            "requested_amount": "500000.00",
            "fiscal_year": "2024",
            "justification": "Test justification",
        }
        response = admin_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_201_CREATED
        assert BudgetRequest.objects.filter(project=project).exists()

    def test_submit_budget_request(self, admin_client, project_type, location, department):
        """Test submitting a budget request."""
        project = ProjectFactory(
            project_type=project_type,
            location=location,
            implementing_department=department,
        )
        budget_request = BudgetRequestFactory(project=project, status="draft")
        url = reverse("api:budget:budget-request-submit", kwargs={"uuid": budget_request.uuid})
        response = admin_client.post(url)

        assert response.status_code == status.HTTP_200_OK
        budget_request.refresh_from_db()
        assert budget_request.status == "submitted"

    def test_approve_budget_request(self, admin_client, project_type, location, department):
        """Test approving a budget request."""
        project = ProjectFactory(
            project_type=project_type,
            location=location,
            implementing_department=department,
        )
        budget_request = BudgetRequestFactory(project=project, status="submitted")
        url = reverse("api:budget:budget-request-approve", kwargs={"uuid": budget_request.uuid})
        data = {
            "approved_amount": "450000.00",
            "remarks": "Approved with adjustments",
        }
        response = admin_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_200_OK
        budget_request.refresh_from_db()
        assert budget_request.status == "approved"
        assert budget_request.approved_amount is not None
        project.refresh_from_db()
        assert project.is_active is True

    def test_reject_budget_request(self, admin_client, project_type, location, department):
        """Test rejecting a budget request."""
        project = ProjectFactory(
            project_type=project_type,
            location=location,
            implementing_department=department,
        )
        budget_request = BudgetRequestFactory(project=project, status="submitted")
        url = reverse("api:budget:budget-request-reject", kwargs={"uuid": budget_request.uuid})
        data = {"remarks": "Insufficient justification"}
        response = admin_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_200_OK
        budget_request.refresh_from_db()
        assert budget_request.status == "rejected"

    def test_cannot_edit_approved_budget(self, admin_client, project_type, location, department):
        """Test that approved budget requests cannot be edited."""
        project = ProjectFactory(
            project_type=project_type,
            location=location,
            implementing_department=department,
        )
        budget_request = BudgetRequestFactory(project=project, status="approved")
        url = reverse("api:budget:budget-request-detail", kwargs={"uuid": budget_request.uuid})
        data = {"requested_amount": "600000.00"}
        response = admin_client.patch(url, data)

        # DRF returns 422 for business rule violations
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_filter_budget_by_status(self, admin_client, project_type, location, department):
        """Test filtering budget requests by status."""
        # Create separate projects for each budget request (one-to-one relationship)
        project1 = ProjectFactory(
            project_type=project_type,
            location=location,
            implementing_department=department,
        )
        project2 = ProjectFactory(
            project_type=project_type,
            location=location,
            implementing_department=department,
        )
        BudgetRequestFactory(project=project1, status="draft")
        BudgetRequestFactory(project=project2, status="approved")

        url = reverse("api:budget:budget-request-list")
        response = admin_client.get(url, {"status": "draft"})

        assert response.status_code == status.HTTP_200_OK
        assert all(item["status"] == "draft" for item in response.data["data"])
