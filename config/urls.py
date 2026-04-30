from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include
from django.urls import path
from drf_spectacular.views import SpectacularAPIView
from drf_spectacular.views import SpectacularRedocView
from drf_spectacular.views import SpectacularSwaggerView
from rest_framework.permissions import AllowAny
from rest_framework.permissions import IsAdminUser

urlpatterns = [
    path(settings.ADMIN_URL, admin.site.urls),
    *static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT),
]

# Determine permission classes based on environment
schema_permission_classes = [AllowAny] if settings.DEBUG else [IsAdminUser]

urlpatterns += [
    # API v1 - Versioned API endpoints
    path("api/v1/", include("config.api_router")),
    # API Schema and Documentation (versioned)
    path(
        "api/v1/schema/",
        SpectacularAPIView.as_view(permission_classes=schema_permission_classes),
        name="api-schema",
    ),
    path(
        "api/v1/docs/",
        SpectacularSwaggerView.as_view(
            url_name="api-schema",
            permission_classes=schema_permission_classes,
        ),
        name="api-docs",
    ),
    path(
        "api/v1/redoc/",
        SpectacularRedocView.as_view(
            url_name="api-schema",
            permission_classes=schema_permission_classes,
        ),
        name="api-redoc",
    ),
]

if settings.DEBUG:
    if "debug_toolbar" in settings.INSTALLED_APPS:
        import debug_toolbar

        urlpatterns = [
            path("__debug__/", include(debug_toolbar.urls)),
            *urlpatterns,
        ]
