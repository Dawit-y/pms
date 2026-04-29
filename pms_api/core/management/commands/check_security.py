"""
Management command to check security configuration.
"""

from django.conf import settings
from django.core.management.base import BaseCommand

SECRET_KEY_LENGTH = 50
YEAR_IN_SECONDS = 31536000
HOUR_IN_SECONDS = 3600


class Command(BaseCommand):
    help = "Check security configuration and provide recommendations"

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("=== Security Configuration Check ===\n"))

        checks = [
            self.check_debug(),
            self.check_secret_key(),
            self.check_allowed_hosts(),
            self.check_https(),
            self.check_hsts(),
            self.check_cookies(),
            self.check_cors(),
            self.check_csp(),
            self.check_throttling(),
            self.check_jwt(),
        ]

        passed = sum(checks)
        total = len(checks)

        self.stdout.write(f"\n{'=' * 50}")
        self.stdout.write(
            self.style.SUCCESS(f"Passed: {passed}/{total} checks"),
        )

        if passed == total:
            self.stdout.write(
                self.style.SUCCESS("✓ All security checks passed!"),
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    f"⚠ {total - passed} security issue(s) found. Please review.",
                ),
            )

    def check_debug(self):
        """Check if DEBUG is disabled in production."""
        self.stdout.write("\n1. DEBUG Mode:")
        if settings.DEBUG:
            self.stdout.write(
                self.style.WARNING(
                    "  ⚠ DEBUG is enabled. Disable in production!",
                ),
            )
            return False
        self.stdout.write(self.style.SUCCESS("  ✓ DEBUG is disabled"))
        return True

    def check_secret_key(self):
        """Check if SECRET_KEY is set and not default."""
        self.stdout.write("\n2. SECRET_KEY:")
        if not settings.SECRET_KEY:
            self.stdout.write(
                self.style.ERROR("  ✗ SECRET_KEY is not set!"),
            )
            return False
        if len(settings.SECRET_KEY) < SECRET_KEY_LENGTH:
            self.stdout.write(
                self.style.WARNING(
                    "  ⚠ SECRET_KEY seems short. Use a longer key.",
                ),
            )
            return False
        self.stdout.write(self.style.SUCCESS("  ✓ SECRET_KEY is configured"))
        return True

    def check_allowed_hosts(self):
        """Check if ALLOWED_HOSTS is configured."""
        self.stdout.write("\n3. ALLOWED_HOSTS:")
        if not settings.ALLOWED_HOSTS or settings.ALLOWED_HOSTS == ["*"]:
            self.stdout.write(
                self.style.WARNING(
                    "  ⚠ ALLOWED_HOSTS is not properly configured",
                ),
            )
            return False
        self.stdout.write(
            self.style.SUCCESS(
                f"  ✓ ALLOWED_HOSTS: {', '.join(settings.ALLOWED_HOSTS)}",
            ),
        )
        return True

    def check_https(self):
        """Check HTTPS/SSL configuration."""
        self.stdout.write("\n4. HTTPS/SSL:")
        issues = []

        if not getattr(settings, "SECURE_SSL_REDIRECT", False):
            issues.append("SECURE_SSL_REDIRECT is disabled")

        if not getattr(settings, "SESSION_COOKIE_SECURE", False):
            issues.append("SESSION_COOKIE_SECURE is disabled")

        if not getattr(settings, "CSRF_COOKIE_SECURE", False):
            issues.append("CSRF_COOKIE_SECURE is disabled")

        if issues:
            for issue in issues:
                self.stdout.write(self.style.WARNING(f"  ⚠ {issue}"))
            return False

        self.stdout.write(self.style.SUCCESS("  ✓ HTTPS/SSL properly configured"))
        return True

    def check_hsts(self):
        """Check HSTS configuration."""
        self.stdout.write("\n5. HSTS (HTTP Strict Transport Security):")
        hsts_seconds = getattr(settings, "SECURE_HSTS_SECONDS", 0)

        if hsts_seconds == 0:
            self.stdout.write(
                self.style.WARNING("  ⚠ HSTS is not enabled"),
            )
            return False

        if hsts_seconds < YEAR_IN_SECONDS:  # 1 year
            self.stdout.write(
                self.style.WARNING(
                    f"  ⚠ HSTS duration is {hsts_seconds}s. Recommended: 31536000s (1 year)",
                ),
            )

        self.stdout.write(
            self.style.SUCCESS(f"  ✓ HSTS enabled ({hsts_seconds}s)"),
        )
        return True

    def check_cookies(self):
        """Check cookie security settings."""
        self.stdout.write("\n6. Cookie Security:")
        issues = []

        if not getattr(settings, "SESSION_COOKIE_HTTPONLY", False):
            issues.append("SESSION_COOKIE_HTTPONLY is disabled")

        if not getattr(settings, "CSRF_COOKIE_HTTPONLY", False):
            issues.append("CSRF_COOKIE_HTTPONLY is disabled")

        samesite = getattr(settings, "SESSION_COOKIE_SAMESITE", None)
        if samesite not in ["Lax", "Strict"]:
            issues.append(f"SESSION_COOKIE_SAMESITE is '{samesite}' (use 'Lax' or 'Strict')")

        if issues:
            for issue in issues:
                self.stdout.write(self.style.WARNING(f"  ⚠ {issue}"))
            return False

        self.stdout.write(self.style.SUCCESS("  ✓ Cookies properly secured"))
        return True

    def check_cors(self):
        """Check CORS configuration."""
        self.stdout.write("\n7. CORS Configuration:")

        if getattr(settings, "CORS_ALLOW_ALL_ORIGINS", False):
            self.stdout.write(
                self.style.WARNING(
                    "  ⚠ CORS_ALLOW_ALL_ORIGINS is True. Restrict in production!",
                ),
            )
            return False

        origins = getattr(settings, "CORS_ALLOWED_ORIGINS", [])
        if origins:
            self.stdout.write(
                self.style.SUCCESS(
                    f"  ✓ CORS restricted to: {', '.join(origins)}",
                ),
            )
            return True

        self.stdout.write(
            self.style.WARNING("  ⚠ CORS_ALLOWED_ORIGINS is empty"),
        )
        return False

    def check_csp(self):
        """Check Content Security Policy configuration."""
        self.stdout.write("\n8. Content Security Policy (CSP):")

        # Django 6 uses SECURE_CSP setting
        csp_config = getattr(settings, "SECURE_CSP", None)
        if not csp_config:
            self.stdout.write(
                self.style.WARNING("  ⚠ CSP is not configured"),
            )
            return False

        self.stdout.write(self.style.SUCCESS("  ✓ CSP is configured (Django 6 built-in):"))

        # Show key directives
        key_directives = [
            ("default-src", "Default source"),
            ("script-src", "Script source"),
            ("style-src", "Style source"),
            ("frame-ancestors", "Frame ancestors"),
        ]

        for directive, description in key_directives:
            value = csp_config.get(directive)
            if value:
                # Convert CSP constants to readable strings
                readable_values = []
                for v in value:
                    if hasattr(v, "value"):  # CSP enum
                        readable_values.append(v.value)
                    else:
                        readable_values.append(str(v))
                self.stdout.write(f"    - {description}: {', '.join(readable_values)}")

        return True

    def check_throttling(self):
        """Check rate limiting configuration."""
        self.stdout.write("\n9. Rate Limiting:")

        throttle_classes = settings.REST_FRAMEWORK.get("DEFAULT_THROTTLE_CLASSES", [])
        if not throttle_classes:
            self.stdout.write(
                self.style.WARNING("  ⚠ No throttling configured"),
            )
            return False

        rates = settings.REST_FRAMEWORK.get("DEFAULT_THROTTLE_RATES", {})
        self.stdout.write(self.style.SUCCESS("  ✓ Throttling enabled:"))
        for scope, rate in rates.items():
            self.stdout.write(f"    - {scope}: {rate}")

        return True

    def check_jwt(self):
        """Check JWT configuration."""
        self.stdout.write("\n10. JWT Configuration:")

        jwt_settings = getattr(settings, "SIMPLE_JWT", {})

        access_lifetime = jwt_settings.get("ACCESS_TOKEN_LIFETIME")
        if access_lifetime and access_lifetime.total_seconds() > HOUR_IN_SECONDS:  # 1 hour
            self.stdout.write(
                self.style.WARNING(
                    f"  ⚠ ACCESS_TOKEN_LIFETIME is {access_lifetime}. Consider shorter duration.",
                ),
            )

        if not jwt_settings.get("ROTATE_REFRESH_TOKENS", False):
            self.stdout.write(
                self.style.WARNING("  ⚠ ROTATE_REFRESH_TOKENS is disabled"),
            )
            return False

        if not jwt_settings.get("BLACKLIST_AFTER_ROTATION", False):
            self.stdout.write(
                self.style.WARNING("  ⚠ BLACKLIST_AFTER_ROTATION is disabled"),
            )
            return False

        self.stdout.write(self.style.SUCCESS("  ✓ JWT properly configured"))
        return True
