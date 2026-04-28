from rest_framework import status
from rest_framework.exceptions import APIException


class UserEmailRequiredException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "USER_EMAIL_REQUIRED"
    default_detail = "Users must have an email address"


class UserNotFoundException(APIException):
    status_code = status.HTTP_404_NOT_FOUND
    default_code = "USER_NOT_FOUND"
    default_detail = "User not found"
