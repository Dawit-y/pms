"""
Tests for Issue Comment API.
"""

import pytest
from django.urls import reverse
from rest_framework import status

from pms_api.project_data.models import IssueComment
from pms_api.project_data.tests.factories import IssueCommentFactory
from pms_api.project_data.tests.factories import IssueFactory
from pms_api.projects.tests.factories import ProjectFactory


@pytest.mark.django_db
class TestIssueCommentsAPI:
    def test_add_issue_comment(
        self,
        admin_client,
        superuser,
        project_type,
        location,
        department,
    ):
        project = ProjectFactory(
            project_type=project_type,
            location=location,
            implementing_department=department,
        )

        issue = IssueFactory(project=project)

        url = reverse(
            "api:project_data:issue-comments",
            kwargs={"uuid": issue.uuid},
        )

        data = {
            "body": "This is my first comment.",
        }

        response = admin_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_201_CREATED
        assert IssueComment.objects.count() == 1

        comment = IssueComment.objects.get()

        assert comment.issue == issue
        assert comment.body == "This is my first comment."
        assert comment.created_by == superuser

    def test_cannot_add_empty_comment(
        self,
        admin_client,
        project_type,
        location,
        department,
    ):
        project = ProjectFactory(
            project_type=project_type,
            location=location,
            implementing_department=department,
        )

        issue = IssueFactory(project=project)

        url = reverse(
            "api:project_data:issue-comments",
            kwargs={"uuid": issue.uuid},
        )

        data = {
            "body": "   ",
        }

        response = admin_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert IssueComment.objects.count() == 0

    def test_issue_detail_includes_comments(
        self,
        admin_client,
        project_type,
        location,
        department,
    ):
        project = ProjectFactory(
            project_type=project_type,
            location=location,
            implementing_department=department,
        )

        issue = IssueFactory(project=project)

        IssueCommentFactory(
            issue=issue,
            body="First comment",
        )
        IssueCommentFactory(
            issue=issue,
            body="Second comment",
        )

        url = reverse(
            "api:project_data:issue-detail",
            kwargs={"uuid": issue.uuid},
        )

        response = admin_client.get(url)

        assert response.status_code == status.HTTP_200_OK

        comments = response.data["data"]["comments"]
        assert len(comments) == 2

        bodies = {comment["body"] for comment in comments}

        assert bodies == {
            "First comment",
            "Second comment",
        }

    def test_add_comment_requires_authentication(
        self,
        api_client,
        project_type,
        location,
        department,
    ):
        project = ProjectFactory(
            project_type=project_type,
            location=location,
            implementing_department=department,
        )

        issue = IssueFactory(project=project)

        url = reverse(
            "api:project_data:issue-comments",
            kwargs={"uuid": issue.uuid},
        )

        data = {
            "body": "This is my first comment.",
        }

        response = api_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert IssueComment.objects.count() == 0
