"""
Custom throttling classes for enterprise-level rate limiting.

Provides multiple layers of rate limiting:
- Burst protection: Prevents rapid-fire requests
- Sustained rate limiting: Daily/hourly limits
- Endpoint-specific throttling: Custom limits for sensitive endpoints
"""

from rest_framework.throttling import UserRateThrottle


class BurstRateThrottle(UserRateThrottle):
    """
    Burst rate throttle to prevent rapid-fire requests.
    Limits users to 60 requests per minute.
    """

    scope = "burst"


class SustainedRateThrottle(UserRateThrottle):
    """
    Sustained rate throttle for daily limits.
    Limits users to 10,000 requests per day.
    """

    scope = "sustained"


class AuthRateThrottle(UserRateThrottle):
    """
    Throttle for authentication endpoints.
    Stricter limits to prevent brute force attacks.
    """

    scope = "auth"


class PasswordResetRateThrottle(UserRateThrottle):
    """
    Throttle for password reset endpoints.
    Very strict limits to prevent abuse.
    """

    scope = "password_reset"


class AdminRateThrottle(UserRateThrottle):
    """
    Higher rate limits for admin users.
    """

    scope = "admin"

    def allow_request(self, request, view):
        """Only apply to admin users."""
        if request.user and request.user.is_authenticated and request.user.is_staff:
            return super().allow_request(request, view)
        # Non-admin users fall through to other throttles
        return True
