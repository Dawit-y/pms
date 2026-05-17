"""
Serializers for report metadata and report job state.
"""

from rest_framework import serializers
from rest_framework.reverse import reverse

from .models import ReportJob
from .signing import make_download_token


class ReportDefinitionSerializer(serializers.Serializer):
    """The shape returned by `GET /reports/` and `GET /reports/{code}/`."""

    code = serializers.CharField()
    name_en = serializers.CharField()
    name_am = serializers.CharField(allow_blank=True)
    name_or = serializers.CharField(allow_blank=True)
    description = serializers.CharField(allow_blank=True)
    permission_codename = serializers.CharField(allow_blank=True)
    columns = serializers.SerializerMethodField()
    filter_schema = serializers.SerializerMethodField()
    pdf_orientation = serializers.CharField()
    pdf_page_size = serializers.CharField()

    def get_columns(self, definition) -> list:
        return definition.get_column_dicts()

    def get_filter_schema(self, definition) -> dict:
        return definition.get_filter_schema()


class ExportRequestSerializer(serializers.Serializer):
    """Body for `POST /reports/{code}/export/`."""

    format = serializers.ChoiceField(choices=[c[0] for c in ReportJob.FORMAT_CHOICES])
    filters = serializers.DictField(child=serializers.JSONField(), required=False, default=dict)
    include_summary = serializers.BooleanField(required=False, default=False)


class ReportJobSerializer(serializers.ModelSerializer):
    download_url = serializers.SerializerMethodField()
    status_url = serializers.SerializerMethodField()
    requested_by = serializers.CharField(source="created_by.email", read_only=True)

    class Meta:
        model = ReportJob
        fields = (
            "uuid",
            "report_code",
            "format",
            "status",
            "progress",
            "params",
            "row_count",
            "file_size",
            "error_message",
            "celery_task_id",
            "started_at",
            "finished_at",
            "expires_at",
            "created_at",
            "requested_by",
            "status_url",
            "download_url",
        )
        read_only_fields = fields

    def get_status_url(self, obj) -> str | None:
        request = self.context.get("request")
        if request is None:
            return None
        return reverse(
            "api:reports:reportjob-detail",
            kwargs={"uuid": obj.uuid},
            request=request,
        )

    def get_download_url(self, obj) -> str | None:
        if obj.status != ReportJob.STATUS_SUCCESS or not obj.file:
            return None
        request = self.context.get("request")
        token = make_download_token(obj)
        path = reverse(
            "api:reports:reportjob-download",
            kwargs={"uuid": obj.uuid},
            request=request,
        )
        sep = "&" if "?" in path else "?"
        return f"{path}{sep}t={token}"
