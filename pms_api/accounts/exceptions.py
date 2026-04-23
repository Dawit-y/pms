from pms_api.core.exceptions import BaseAPIException


class UserEmailRequiredException(BaseAPIException):
    default_code = "USER_EMAIL_REQUIRED"
    default_message = "Users must have an email address"


class UserNotFoundException(BaseAPIException):
    status_code = 404
    default_code = "USER_NOT_FOUND"
    default_message = "User not found"
