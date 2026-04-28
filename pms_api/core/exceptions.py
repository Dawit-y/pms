"""
Centralised exception classes and a DRF custom exception handler.
Every API error returns a consistent envelope:

    {
        "success": false,
        "error": {
            "code":    "RESOURCE_NOT_FOUND",
            "message": "Project with uuid=... does not exist.",
            "detail":  { ... }          ← optional field-level errors
        }
    }
"""

import logging
import traceback

from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import exception_handler

# ─── Custom exception classes ─────────────────────────────────────────────────


class ResourceNotFound(APIException):
    status_code = status.HTTP_404_NOT_FOUND
    default_code = "RESOURCE_NOT_FOUND"
    default_detail = "The requested resource was not found."


class PermissionDenied(APIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_code = "PERMISSION_DENIED"
    default_detail = "You do not have permission to perform this action."


class BusinessRuleViolation(APIException):
    """Use for domain-rule errors: e.g. 'cannot edit after approval'."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_code = "BUSINESS_RULE_VIOLATION"
    default_detail = "This action violates a business rule."


class ConflictError(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "CONFLICT"
    default_detail = "A conflict occurred with the current state of the resource."


class SoftDeletedResourceError(APIException):
    status_code = status.HTTP_410_GONE
    default_code = "RESOURCE_DELETED"
    default_detail = "This resource has been deleted. An admin can restore it."


# ─── Custom exception handler ─────────────────────────────────────────────────


def custom_exception_handler(exc, context):
    """
    Replace DRF's default exception handler so every error uses our envelope.
    Register in settings.py:
        REST_FRAMEWORK = {
            'EXCEPTION_HANDLER': 'core.exceptions.custom_exception_handler',
        }
    """
    logger = logging.getLogger(__name__)

    response = exception_handler(exc, context)

    if response is None:
        # Unhandled server error — log the full traceback for debugging
        logger.error(
            "Unhandled exception: %s\n%s",
            str(exc),
            traceback.format_exc(),
        )
        return Response(
            {
                "success": False,
                "error": {
                    "code": "INTERNAL_SERVER_ERROR",
                    "message": "An unexpected error occurred.",
                },
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    code = getattr(exc, "default_code", "ERROR")
    message = str(exc.detail) if hasattr(exc, "detail") else str(exc)
    detail = None

    # ValidationError comes with field-level details
    if isinstance(response.data, dict) and any(
        isinstance(v, list) for v in response.data.values()
    ):
        detail = response.data
        message = "Validation failed. Check the 'detail' field for field-level errors."

    response.data = {
        "success": False,
        "error": {
            "code": code.upper(),
            "message": message,
            **({"detail": detail} if detail else {}),
        },
    }
    return response
