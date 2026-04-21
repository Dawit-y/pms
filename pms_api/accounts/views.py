import logging
from datetime import timedelta

from django.conf import settings
from djoser.views import UserViewSet as DjoserUserViewSet
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework_simplejwt.exceptions import InvalidToken
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.views import TokenRefreshView

from .serializers import CustomTokenObtainPairSerializer

logger = logging.getLogger(__name__)


class CustomTokenObtainPairView(TokenObtainPairView):
    """
    Custom JWT login view that stores refresh token in HTTP-only cookie
    and returns only access token in response body.
    """

    serializer_class = CustomTokenObtainPairSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)

        try:
            serializer.is_valid(raise_exception=True)
        except TokenError as e:
            raise InvalidToken(e.args[0]) from e

        # Get tokens from serializer
        tokens = serializer.validated_data

        # Extract refresh token to set as cookie
        refresh_token = tokens.pop("refresh")

        # Create response with only access token and user data
        response = Response(tokens, status=status.HTTP_200_OK)

        # Set refresh token as HTTP-only cookie
        max_age = timedelta(days=7).total_seconds()  # 7 days
        response.set_cookie(
            key="refresh_token",
            value=refresh_token,
            max_age=int(max_age),
            httponly=True,
            secure=not settings.DEBUG,  # True in production (HTTPS only)
            samesite="Lax",  # or 'Strict' for more security
            path="/",
        )

        return response


class CustomTokenRefreshView(TokenRefreshView):
    """
    Custom JWT refresh view that reads refresh token from HTTP-only cookie
    instead of request body.
    """

    def post(self, request, *args, **kwargs):
        # Get refresh token from cookie
        refresh_token = request.COOKIES.get("refresh_token")

        if not refresh_token:
            return Response(
                {"detail": "Refresh token not found in cookies."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        try:
            # Validate and refresh the token
            refresh = RefreshToken(refresh_token)
            access_token = str(refresh.access_token)

            return Response(
                {"access": access_token},
                status=status.HTTP_200_OK,
            )
        except TokenError as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_401_UNAUTHORIZED,
            )


class CustomTokenLogoutView(TokenRefreshView):
    """
    Logout view that blacklists the refresh token and clears the cookie.
    """

    def post(self, request, *args, **kwargs):
        refresh_token = request.COOKIES.get("refresh_token")

        if not refresh_token:
            return Response(
                {"detail": "No active session found."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            # Blacklist the refresh token
            token = RefreshToken(refresh_token)
            token.blacklist()
        except TokenError:
            logger.warning("Token already invalid")
        except Exception:
            logger.exception("Unexpected error while blacklisting token")

        # Create response and clear cookie
        response = Response(
            {"detail": "Successfully logged out."},
            status=status.HTTP_200_OK,
        )
        response.delete_cookie("refresh_token", path="/")

        return response


class UserViewSet(DjoserUserViewSet):
    """
    Extended Djoser UserViewSet with custom actions.
    """

    @action(detail=False, methods=["get"])
    def me(self, request):
        """Get current user with permissions."""
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)
