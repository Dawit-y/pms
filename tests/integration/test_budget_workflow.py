"""
Integration test for complete budget approval workflow.
"""

import pytest
from django.urls import reverse
from rest_framework import status

from pms_api.budget.models import BudgetRequest
from pms_api.projects.models import Project


@pytest.mark.django_db
@pytest.mark.integration
class TestBudgetApprovalWorkflow:
    """Test the complete budget request and approval workflow."""

    def test_complete_budget_workflow(
        self,
        admin_client,
        project_type,
        location,
        department,
    ):
        """
        Test complete workflow:
        1. Create project
        2. Create budget request
        3. Submit budget request
        4. Approve budget request
        5. Verify project is activated
        """
        # Step 1: Create project
        project_url = reverse("api:projects:project-list")
        project_data = {
            "code": "WORKFLOW-001",
            "title": "Integration Test Project",
            "description": "Testing complete workflow",
            "project_type": project_type.id,
            "location": location.id,
            "implementing_department": department.id,
            "total_budget": "1000000.00",
        }
        project_response = admin_client.post(project_url, project_data, format="json")
        assert project_response.status_code == status.HTTP_201_CREATED
        project_uuid = project_response.data["data"]["uuid"]

        # Verify project is not active initially
        project = Project.objects.get(uuid=project_uuid)
        assert project.is_active is False

        # Step 2: Create budget request
        budget_url = reverse("api:budget:budget-request-list")
        budget_data = {
            "project": project.id,
            "requested_amount": "1000000.00",
            "fiscal_year": "2024",
            "justification": "Integration test budget request",
        }
        budget_response = admin_client.post(budget_url, budget_data, format="json")
        assert budget_response.status_code == status.HTTP_201_CREATED
        budget_uuid = budget_response.data["data"]["uuid"]

        # Verify budget is in draft status
        budget = BudgetRequest.objects.get(uuid=budget_uuid)
        assert budget.status == "draft"

        # Step 3: Submit budget request
        submit_url = reverse("api:budget:budget-request-submit", kwargs={"uuid": budget_uuid})
        submit_response = admin_client.post(submit_url)
        assert submit_response.status_code == status.HTTP_200_OK

        # Verify status changed to submitted
        budget.refresh_from_db()
        assert budget.status == "submitted"

        # Step 4: Approve budget request
        approve_url = reverse("api:budget:budget-request-approve", kwargs={"uuid": budget_uuid})
        approve_data = {
            "approved_amount": "950000.00",
            "remarks": "Approved with minor adjustment",
        }
        approve_response = admin_client.post(approve_url, approve_data, format="json")
        assert approve_response.status_code == status.HTTP_200_OK

        # Step 5: Verify final state
        budget.refresh_from_db()
        project.refresh_from_db()

        assert budget.status == "approved"
        assert str(budget.approved_amount) == "950000.00"
        assert project.is_active is True
        assert project.current_status is not None
        assert project.current_status.status == "budget_approved"

    def test_budget_rejection_workflow(
        self,
        admin_client,
        project_type,
        location,
        department,
    ):
        """
        Test budget rejection workflow:
        1. Create project and budget
        2. Submit budget
        3. Reject budget
        4. Verify project remains inactive
        """
        # Create project
        project_url = reverse("api:projects:project-list")
        project_data = {
            "code": "REJECT-001",
            "title": "Rejection Test Project",
            "project_type": project_type.id,
            "location": location.id,
            "implementing_department": department.id,
            "total_budget": "500000.00",
        }
        project_response = admin_client.post(project_url, project_data, format="json")
        project_uuid = project_response.data["data"]["uuid"]

        # Create and submit budget
        budget_url = reverse("api:budget:budget-request-list")
        project = Project.objects.get(uuid=project_uuid)
        budget_data = {
            "project": project.id,
            "requested_amount": "500000.00",
            "fiscal_year": "2024",
            "justification": "Test rejection",
        }
        budget_response = admin_client.post(budget_url, budget_data, format="json")
        budget_uuid = budget_response.data["data"]["uuid"]

        submit_url = reverse("api:budget:budget-request-submit", kwargs={"uuid": budget_uuid})
        admin_client.post(submit_url)

        # Reject budget
        reject_url = reverse("api:budget:budget-request-reject", kwargs={"uuid": budget_uuid})
        reject_data = {"remarks": "Insufficient justification"}
        reject_response = admin_client.post(reject_url, reject_data, format="json")
        assert reject_response.status_code == status.HTTP_200_OK

        # Verify final state
        budget = BudgetRequest.objects.get(uuid=budget_uuid)
        project.refresh_from_db()

        assert budget.status == "rejected"
        assert project.is_active is False
