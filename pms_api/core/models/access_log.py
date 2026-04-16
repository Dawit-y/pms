from django.contrib.contenttypes.models import ContentType
from django.db import models


class AccessLog(models.Model):
    """
    Immutable audit log — never soft-deleted, never edited.
    Tracks every mutating request (POST, PUT, PATCH, DELETE).
    """

    HTTP_METHODS = [
        ("POST", "POST"),
        ("PUT", "PUT"),
        ("PATCH", "PATCH"),
        ("DELETE", "DELETE"),
    ]

    user = models.ForeignKey(
        "accounts.User",
        null=True,
        on_delete=models.SET_NULL,
        related_name="access_logs",
    )
    method = models.CharField(max_length=10, choices=HTTP_METHODS)
    endpoint = models.CharField(max_length=500)
    ip_address = models.GenericIPAddressField(null=True)
    user_agent = models.CharField(max_length=512, blank=True)
    request_body = models.JSONField(
        null=True,
        blank=True,
    )  # sanitized (passwords stripped)
    response_status = models.PositiveSmallIntegerField(null=True)
    duration_ms = models.PositiveIntegerField(null=True)  # request duration

    # What model/object was affected
    content_type = models.ForeignKey(
        ContentType,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    object_id = models.PositiveIntegerField(null=True, blank=True)

    session_key = models.CharField(max_length=64, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        app_label = "core"
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["user", "timestamp"]),
            models.Index(fields=["endpoint", "method"]),
        ]

    def __str__(self):
        return f"[{self.timestamp}] {self.method}"
