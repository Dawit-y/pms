"""
Tests for pagination utilities.
"""

from pms_api.core.pagination import StandardPagination
from pms_api.core.pagination import success_response


class TestStandardPagination:
    def test_default_page_size(self):
        """Test default page size is set correctly."""
        pagination = StandardPagination()
        assert pagination.page_size == 25

    def test_max_page_size(self):
        """Test max page size limit."""
        pagination = StandardPagination()
        assert pagination.max_page_size == 200


class TestSuccessResponse:
    def test_success_response_with_data(self):
        """Test success response with data."""
        data = {"id": 1, "name": "Test"}
        response = success_response(data)

        assert response["success"] is True
        assert response["data"] == data

    def test_success_response_with_message(self):
        """Test success response with custom message."""
        data = {"id": 1}
        message = "Operation successful"
        response = success_response(data, message=message)

        assert response["success"] is True
        assert response["message"] == message

    def test_success_response_without_data(self):
        """Test success response without data."""
        response = success_response()

        assert response["success"] is True
        assert "data" not in response
