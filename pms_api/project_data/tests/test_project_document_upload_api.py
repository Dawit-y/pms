import pytest
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status

from pms_api.projects.tests.factories import ProjectFactory


@pytest.mark.django_db
class TestProjectDocumentAPI:
    def test_upload_valid_pdf(
        self,
        admin_client,
        project_type,
        location,
        department,
        document_type,
    ):
        project = ProjectFactory(
            project_type=project_type,
            location=location,
            implementing_department=department,
        )
        uploaded_file = SimpleUploadedFile(
            "test.pdf",
            b"fake pdf content",
            content_type="application/pdf",
        )
        data = {
            "project": project.id,
            "title": "Test PDF",
            "document_type": document_type.id,
            "file": uploaded_file,
        }
        url = reverse("api:project_data:project-document-list")

        response = admin_client.post(
            url,
            data,
            format="multipart",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["data"]["title"] == "Test PDF"
        assert response.data["data"]["file_size"] is not None
        assert response.data["data"]["file_url"] is not None

    def test_upload_invalid_extension(
        self,
        admin_client,
        project_type,
        location,
        department,
        document_type,
    ):
        project = ProjectFactory(
            project_type=project_type,
            location=location,
            implementing_department=department,
        )
        uploaded_file = SimpleUploadedFile(
            "virus.exe",
            b"fake exe",
            content_type="application/octet-stream",
        )
        data = {
            "project": project.id,
            "title": "Test PDF",
            "document_type": document_type.id,
            "file": uploaded_file,
        }
        url = reverse("api:project_data:project-document-list")
        response = admin_client.post(
            url,
            data,
            format="multipart",
        )
        assert response.status_code == 400
        # assert "Unsupported file extension" in str(response.data)
        assert (
        "File extension" in response.data["error"]["detail"]["file"][0]
        )

    def test_upload_file_size_exceeded(
        self,
        admin_client,
        project_type,
        location,
        department,
        document_type,
    ):
        project = ProjectFactory(
            project_type=project_type,
            location=location,
            implementing_department=department,
        )
        uploaded_file = SimpleUploadedFile(
            "large.pdf",
            b"x" * (settings.MAX_DOCUMENT_UPLOAD_SIZE + 1),
            content_type="application/pdf",
        )
        data = {
            "project": project.id,
            "title": "Test PDF",
            "document_type": document_type.id,
            "file": uploaded_file,
        }
        url = reverse("api:project_data:project-document-list")
        response = admin_client.post(
            url,
            data,
            format="multipart",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "File size exceeds the limit" in str(response.data)
