# ruff: noqa: ERA001, E501
"""Base settings to build other settings files upon."""

from datetime import timedelta
from pathlib import Path

import environ

# from django.utils.csp import CSP  # Temporarily disabled

BASE_DIR = Path(__file__).resolve(strict=True).parent.parent.parent
# pms_api/
APPS_DIR = BASE_DIR / "pms_api"
env = environ.Env()

READ_DOT_ENV_FILE = env.bool("DJANGO_READ_DOT_ENV_FILE", default=True)
if READ_DOT_ENV_FILE:
    # OS environment variables take precedence over variables from .env
    env.read_env(str(BASE_DIR / ".env"))

# GENERAL
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#debug
DEBUG = env.bool("DJANGO_DEBUG", False)
# Local time zone. Choices are
# http://en.wikipedia.org/wiki/List_of_tz_zones_by_name
# though not all of them may be available with every OS.
# In Windows, this must be set to your system time zone.
TIME_ZONE = "Africa/Addis_Ababa"
# https://docs.djangoproject.com/en/dev/ref/settings/#language-code
LANGUAGE_CODE = "en-us"
# https://docs.djangoproject.com/en/dev/ref/settings/#languages
# from django.utils.translation import gettext_lazy as _
# LANGUAGES = [
#     ('en', _('English')),
#     ('fr-fr', _('French')),
#     ('pt-br', _('Portuguese')),
# ]
# https://docs.djangoproject.com/en/dev/ref/settings/#site-id
SITE_ID = 1
# https://docs.djangoproject.com/en/dev/ref/settings/#use-i18n
USE_I18N = True
# https://docs.djangoproject.com/en/dev/ref/settings/#use-tz
USE_TZ = True
# https://docs.djangoproject.com/en/dev/ref/settings/#locale-paths
LOCALE_PATHS = [str(BASE_DIR / "locale")]

# DATABASES
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#databases
DATABASES = {"default": env.db("DATABASE_URL")}
# Per-request transactions are disabled: CRUD views opt in via @transaction.atomic.
# Wrapping every read in a transaction was adding measurable latency to GETs.
DATABASES["default"]["ATOMIC_REQUESTS"] = False
# Persistent connections — avoids a fresh TCP/SSL handshake to the DB per request.
DATABASES["default"]["CONN_MAX_AGE"] = env.int("CONN_MAX_AGE", default=60)
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True
# https://docs.djangoproject.com/en/stable/ref/settings/#std:setting-DEFAULT_AUTO_FIELD

# URLS
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#root-urlconf
ROOT_URLCONF = "config.urls"
# https://docs.djangoproject.com/en/dev/ref/settings/#wsgi-application
WSGI_APPLICATION = "config.wsgi.application"

# APPS
# ------------------------------------------------------------------------------
DJANGO_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.sites",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # "django.contrib.humanize", # Handy template tags
    "django.contrib.admin",
    "django.forms",
]
THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "django_filters",
    "drf_spectacular",
    "mptt",
    "simple_history",
    "django_celery_beat",
    "django_celery_results",
]

LOCAL_APPS = [
    "pms_api.core",
    "pms_api.accounts",
    "pms_api.lookups",
    "pms_api.budget",
    "pms_api.projects",
    "pms_api.project_data",
    "pms_api.reports",
]
# https://docs.djangoproject.com/en/dev/ref/settings/#installed-apps
INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# MIGRATIONS
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#migration-modules
MIGRATION_MODULES = {"sites": "pms_api.contrib.sites.migrations"}

# AUTHENTICATION
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#authentication-backends
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
]
# https://docs.djangoproject.com/en/dev/ref/settings/#auth-user-model
AUTH_USER_MODEL = "accounts.User"
# # https://docs.djangoproject.com/en/dev/ref/settings/#login-redirect-url
# LOGIN_REDIRECT_URL = "users:redirect"
# # https://docs.djangoproject.com/en/dev/ref/settings/#login-url
# LOGIN_URL = "account_login"

# PASSWORDS
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#password-hashers
PASSWORD_HASHERS = [
    # https://docs.djangoproject.com/en/dev/topics/auth/passwords/#using-argon2-with-django
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
]
# https://docs.djangoproject.com/en/dev/ref/settings/#auth-password-validators
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# MIDDLEWARE
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#middleware
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    # "django.middleware.csp.ContentSecurityPolicyMiddleware",  # Temporarily disabled
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # "simple_history.middleware.HistoryRequestMiddleware",  # Temporarily disabled
    "pms_api.core.middleware.AccessLogMiddleware",
]

# STATIC
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#static-root
STATIC_ROOT = str(BASE_DIR / "staticfiles")
# https://docs.djangoproject.com/en/dev/ref/settings/#static-url
STATIC_URL = "/static/"
# https://docs.djangoproject.com/en/dev/ref/contrib/staticfiles/#std:setting-STATICFILES_DIRS
STATICFILES_DIRS = [str(APPS_DIR / "static")]
# https://docs.djangoproject.com/en/dev/ref/contrib/staticfiles/#staticfiles-finders
STATICFILES_FINDERS = [
    "django.contrib.staticfiles.finders.FileSystemFinder",
    "django.contrib.staticfiles.finders.AppDirectoriesFinder",
]

# MEDIA
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#media-root
MEDIA_ROOT = str(APPS_DIR / "media")
# https://docs.djangoproject.com/en/dev/ref/settings/#media-url
MEDIA_URL = "/media/"

# TEMPLATES
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#templates
TEMPLATES = [
    {
        # https://docs.djangoproject.com/en/dev/ref/settings/#std:setting-TEMPLATES-BACKEND
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        # https://docs.djangoproject.com/en/dev/ref/settings/#dirs
        "DIRS": [str(APPS_DIR / "templates")],
        # https://docs.djangoproject.com/en/dev/ref/settings/#app-dirs
        "APP_DIRS": True,
        "OPTIONS": {
            # https://docs.djangoproject.com/en/dev/ref/settings/#template-context-processors
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.template.context_processors.i18n",
                "django.template.context_processors.media",
                "django.template.context_processors.static",
                "django.template.context_processors.tz",
                "django.contrib.messages.context_processors.messages",
                # "django.template.context_processors.csp",  # CSP nonce support - Temporarily disabled
            ],
        },
    },
]

# https://docs.djangoproject.com/en/dev/ref/settings/#form-renderer
FORM_RENDERER = "django.forms.renderers.TemplatesSetting"

# FIXTURES
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#fixture-dirs
FIXTURE_DIRS = (str(APPS_DIR / "fixtures"),)

# SECURITY
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#session-cookie-httponly
SESSION_COOKIE_HTTPONLY = True
# https://docs.djangoproject.com/en/dev/ref/settings/#csrf-cookie-httponly
CSRF_COOKIE_HTTPONLY = True
# https://docs.djangoproject.com/en/dev/ref/settings/#x-frame-options
X_FRAME_OPTIONS = "DENY"
# https://docs.djangoproject.com/en/dev/ref/settings/#secure-browser-xss-filter
SECURE_BROWSER_XSS_FILTER = False  # Deprecated, modern browsers ignore this
# https://docs.djangoproject.com/en/dev/ref/settings/#secure-content-type-nosniff
SECURE_CONTENT_TYPE_NOSNIFF = True
# Session security
SESSION_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 86400  # 24 hours
SESSION_SAVE_EVERY_REQUEST = False
SESSION_EXPIRE_AT_BROWSER_CLOSE = False
# CSRF security
CSRF_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_USE_SESSIONS = False
# Referrer Policy
SECURE_REFERRER_POLICY = "same-origin"
# Permissions Policy - Restrict browser features
# https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Permissions-Policy
PERMISSIONS_POLICY = {
    "accelerometer": [],
    "camera": [],
    "geolocation": [],
    "gyroscope": [],
    "magnetometer": [],
    "microphone": [],
    "payment": [],
    "usb": [],
}
# Content Security Policy (CSP) - Django 6 built-in
# https://docs.djangoproject.com/en/6.0/ref/middleware/#content-security-policy
# Temporarily disabled for debugging

# SECURE_CSP = {
#     "default-src": [CSP.SELF],
#     "script-src": [CSP.SELF, CSP.NONCE],  # Nonce for inline scripts
#     "style-src": [CSP.SELF, CSP.UNSAFE_INLINE],  # unsafe-inline needed for admin
#     "img-src": [CSP.SELF, "data:", "https:"],
#     "font-src": [CSP.SELF, "data:"],
#     "connect-src": [CSP.SELF],
#     "frame-ancestors": [CSP.NONE],  # Equivalent to X-Frame-Options: DENY
#     "base-uri": [CSP.SELF],
#     "form-action": [CSP.SELF],
# }

# EMAIL
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#email-backend
EMAIL_BACKEND = env(
    "DJANGO_EMAIL_BACKEND",
    default="django.core.mail.backends.smtp.EmailBackend",
)
# https://docs.djangoproject.com/en/dev/ref/settings/#email-timeout
EMAIL_TIMEOUT = 5

# ADMIN
# ------------------------------------------------------------------------------
# Django Admin URL.
ADMIN_URL = "admin/"
# https://docs.djangoproject.com/en/dev/ref/settings/#admins
ADMINS = ['"Dawit Yimer" <dawityimer52@gmail.com>']
# https://docs.djangoproject.com/en/dev/ref/settings/#managers
MANAGERS = ADMINS

# LOGGING
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#logging
# See https://docs.djangoproject.com/en/dev/topics/logging for
# more details on how to customize your logging configuration.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "%(levelname)s %(asctime)s %(module)s %(process)d %(thread)d %(message)s",
        },
    },
    "handlers": {
        "console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {"level": "INFO", "handlers": ["console"]},
}

REDIS_URL = env("REDIS_URL", default="redis://127.0.0.1:6379/0")
REDIS_SSL = REDIS_URL.startswith("rediss://")

# CACHES
# ------------------------------------------------------------------------------
# Redis-backed cache shared by every environment. Test settings override this
# to a local-memory backend so tests don't need a running Redis.
# IGNORE_EXCEPTIONS=True means the app falls through to the database when Redis
# is unreachable rather than raising — the cache is a speedup, not a hard dep.
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_URL,
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "IGNORE_EXCEPTIONS": True,
            "SOCKET_CONNECT_TIMEOUT": 3,
            "SOCKET_TIMEOUT": 3,
            "COMPRESSOR": "django_redis.compressors.zlib.ZlibCompressor",
            "SERIALIZER": "django_redis.serializers.pickle.PickleSerializer",
        },
        "KEY_PREFIX": "pms",
    },
}
DJANGO_REDIS_IGNORE_EXCEPTIONS = True

# Default TTL for the cached model manager (seconds). Models can override.
CACHE_DEFAULT_TIMEOUT = env.int("CACHE_DEFAULT_TIMEOUT", default=60 * 15)

# django-rest-framework
# -------------------------------------------------------------------------------
# django-rest-framework - https://www.django-rest-framework.org/api-guide/settings/
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_PAGINATION_CLASS": "pms_api.core.pagination.StandardPagination",
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "EXCEPTION_HANDLER": "pms_api.core.exceptions.custom_exception_handler",
    # API Versioning
    "DEFAULT_VERSIONING_CLASS": "rest_framework.versioning.URLPathVersioning",
    "DEFAULT_VERSION": "v1",
    "ALLOWED_VERSIONS": ["v1"],
    "VERSION_PARAM": "version",
    # Throttling - Enterprise-level rate limits
    # BurstRateThrottle / SustainedRateThrottle are kept available for explicit
    # opt-in on sensitive views, but they're UserRateThrottle subclasses and
    # running all four globally meant ~16 cache round-trips per request.
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "100/hour",  # Anonymous users: 100 requests per hour
        "user": "1000/hour",  # Authenticated users: 1000 requests per hour
        "burst": "60/minute",  # Burst protection: 60 requests per minute
        "sustained": "10000/day",  # Daily limit: 10000 requests per day
        "auth": "5/minute",  # Authentication endpoints: 5 attempts per minute
        "password_reset": "3/hour",  # Password reset: 3 attempts per hour
        "admin": "2000/hour",  # Admin users: 2000 requests per hour
    },
    # Security settings
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.FormParser",
        "rest_framework.parsers.MultiPartParser",
    ],
    # Limit browsable API to development
    "DEFAULT_METADATA_CLASS": "rest_framework.metadata.SimpleMetadata",
}

# django-cors-headers - https://github.com/adamchainz/django-cors-headers#setup
CORS_URLS_REGEX = r"^/api/.*$"

# By Default swagger ui is available only to admin user(s). You can change permission classes to change that
# See more configuration options at https://drf-spectacular.readthedocs.io/en/latest/settings.html#settings
SPECTACULAR_SETTINGS = {
    "TITLE": "PMS API",
    "DESCRIPTION": "Documentation of API endpoints of PMS",
    "VERSION": "1.0.0",
    "SERVE_PERMISSIONS": ["rest_framework.permissions.AllowAny"],  # Overridden in production
    "SCHEMA_PATH_PREFIX": "/api/v1/",
    "SERVERS": [
        {"url": "http://localhost:8000", "description": "Local Development"},
    ],
    "COMPONENT_SPLIT_REQUEST": True,
    "SORT_OPERATIONS": False,
    "SWAGGER_UI_SETTINGS": {
        "deepLinking": True,
        "persistAuthorization": True,
        "displayOperationId": True,
        "filter": True,
    },
}

# Simple JWT
# -------------------------------------------------------------------------------

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(days=1) if DEBUG else timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": env("DJANGO_SECRET_KEY"),
    "AUTH_HEADER_TYPES": ("Bearer",),
    "AUTH_HEADER_NAME": "HTTP_AUTHORIZATION",
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
    "AUTH_TOKEN_CLASSES": ("rest_framework_simplejwt.tokens.AccessToken",),
    "TOKEN_TYPE_CLAIM": "token_type",
    "TOKEN_OBTAIN_SERIALIZER": "pms_api.accounts.serializer.CustomTokenObtainPairSerializer",
}

# django-simple-history
# -------------------------------------------------------------------------------
# https://django-simple-history.readthedocs.io/en/latest/
SIMPLE_HISTORY_REVERT_DISABLED = False
SIMPLE_HISTORY_HISTORY_ID_USE_UUID = False
SIMPLE_HISTORY_FILEFIELD_TO_CHARFIELD = True

# Celery
# -------------------------------------------------------------------------------
# Broker = Redis (same instance used for caching). Result backend uses
# django-celery-results so task records survive a Redis flush and are visible
# in the Django admin alongside everything else.
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default=REDIS_URL)
CELERY_RESULT_BACKEND = "django-db"
CELERY_CACHE_BACKEND = "default"
CELERY_TIMEZONE = TIME_ZONE
CELERY_ENABLE_UTC = True
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_TIME_LIMIT = 60 * 30
CELERY_TASK_SOFT_TIME_LIMIT = 60 * 25
CELERY_TASK_ACKS_LATE = True
# Long-running export tasks deserve fairness over throughput. With prefetch=1,
# a worker pulls one task at a time so a slow export doesn't block faster ones
# already waiting in the same queue.
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
CELERY_TASK_DEFAULT_QUEUE = "default"
CELERY_TASK_ROUTES = {
    "pms_api.reports.tasks.generate_report": {"queue": "reports"},
    "pms_api.reports.tasks.cleanup_expired_reports": {"queue": "maintenance"},
}
CELERY_RESULT_EXTENDED = True

# Reports
# -------------------------------------------------------------------------------
REPORT_FILE_RETENTION_DAYS = env.int("REPORT_FILE_RETENTION_DAYS", default=7)
REPORT_DOWNLOAD_TOKEN_MAX_AGE = env.int("REPORT_DOWNLOAD_TOKEN_MAX_AGE", default=24 * 3600)
REPORT_MAX_ROWS_XLSX = env.int("REPORT_MAX_ROWS_XLSX", default=200_000)
REPORT_MAX_ROWS_PDF = env.int("REPORT_MAX_ROWS_PDF", default=5000)
# Per-user ceiling on concurrent queued|running jobs — guards against abuse
# that could exhaust the media volume before the daily cleanup runs.
REPORT_MAX_CONCURRENT_PER_USER = env.int("REPORT_MAX_CONCURRENT_PER_USER", default=3)
