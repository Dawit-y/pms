from rest_framework import status
from rest_framework.exceptions import APIException


class BaseAPIException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "error"
    default_message = "Something went wrong"

    def __init__(self, message=None, code=None, details=None):
        self.message = message or self.default_message
        self.code = code or self.default_code
        self.details = details or {}

    def get_full_details(self):
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details,
        }
