"""
Tests for Project API endpoints.
"""

import pytest
from django.urls import reverse
from rest_framework import status

from pms_api.projects.models import Project
from pms_api.projects.tests.factories import ProjectFactory


@pytest.mark.django_db
class TestProjectAPI:
    def test_list_projects_as_admin(self, admin_client, project_type, location, department):
        """Test listing projects as admin."""
        ProjectFactory.create_batch(
            3,
            project_type=project_type,
            location=location,
            implementing_department=department,
        )
        url = reverse("api:projects:project-list")
        response = admin_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["data"]) >= 3

    def test_create_project(self, admin_client, project_type, location, department):
        """Test creating a project."""
        url = reverse("api:projects:project-list")
        data = {
            "code": "PRJ-TEST-001",
            "title": "Test Project",
            "description": "Test Description",
            "project_type": project_type.id,
            "location": location.id,
            "implementing_department": department.id,
            "total_budget": "1000000.00",
        }
        response = admin_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_201_CREATED
        assert Project.objects.filter(code="PRJ-TEST-001").exists()

    def test_retrieve_project_detail(self, admin_client, project_type, location, department):
        """Test retrieving project detail."""
        project = ProjectFactory(
            project_type=project_type,
            location=location,
            implementing_department=department,
        )
        url = reverse("api:projects:project-detail", kwargs={"uuid": project.uuid})
        response = admin_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["code"] == project.code

    def test_update_project(self, admin_client, project_type, location, department):
        """Test updating project information."""
        project = ProjectFactory(
            project_type=project_type,
            location=location,
            implementing_department=department,
        )
        url = reverse("api:projects:project-detail", kwargs={"uuid": project.uuid})
        data = {"title": "Updated Title"}
        response = admin_client.patch(url, data)

        assert response.status_code == status.HTTP_200_OK
        project.refresh_from_db()
        assert project.title == "Updated Title"

    def test_cannot_delete_active_project(self, admin_client, project_type, location, department):
        """Test that active projects cannot be deleted."""
        project = ProjectFactory(
            project_type=project_type,
            location=location,
            implementing_department=department,
            is_active=True,
        )
        url = reverse("api:projects:project-detail", kwargs={"uuid": project.uuid})
        response = admin_client.delete(url)

        # DRF returns 422 for business rule violations
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_project_stats(self, admin_client, project_type, location, department):
        """Test project statistics endpoint."""
        ProjectFactory.create_batch(
            5,
            project_type=project_type,
            location=location,
            implementing_department=department,
        )
        url = reverse("api:projects:project-stats")
        response = admin_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert "total" in response.data["data"]
        assert "active" in response.data["data"]

    def test_filter_projects_by_status(self, admin_client, project_type, location, department):
        """Test filtering projects by status."""
        project = ProjectFactory(
            project_type=project_type,
            location=location,
            implementing_department=department,
            is_active=True,
        )
        url = reverse("api:projects:project-list")
        response = admin_client.get(url, {"is_active": "true"})

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["data"]) >= 1

    def test_search_projects(self, admin_client, project_type, location, department):
        """Test searching projects by code or title."""
        project = ProjectFactory(
            code="SEARCH-001",
            title="Searchable Project",
            project_type=project_type,
            location=location,
            implementing_department=department,
        )
        url = reverse("api:projects:project-list")
        response = admin_client.get(url, {"search": "SEARCH"})

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["data"]) >= 1
