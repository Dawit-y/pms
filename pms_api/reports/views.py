"""
Report definition + report job APIs.

`ReportViewSet` is a custom GenericViewSet because reports are not Django
models — they're registry-resident classes. `ReportJobViewSet` extends the
project's standard `BaseModelViewSet` shape but skips create/update/delete
through REST; jobs are only created by the `/export/` action below.
"""

import logging

from django.conf import settings
from django.core.signing import BadSignature
from django.db import transaction
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import mixins
from rest_framework import status
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from pms_api.core.exceptions import BusinessRuleViolation
from pms_api.core.exceptions import PermissionDenied as ApiPermissionDenied
from pms_api.core.exceptions import ResourceNotFound
from pms_api.core.pagination import StandardPagination
from pms_api.core.pagination import success_response
from pms_api.core.permissions import ActionPermissionMixin

from .models import ReportJob
from .permissions import IsReportJobOwner
from .registry import registry
from .serializers import ExportRequestSerializer
from .serializers import ReportDefinitionSerializer
from .serializers import ReportJobSerializer
from .signing import verify_download_token

logger = logging.getLogger(__name__)


def _require_report_perm(user, definition) -> None:
    """Raise the project's PermissionDenied if `user` can't run `definition`."""
    perm = definition.permission_codename
    if perm and not user.has_perm(perm):
        msg = f"You don't have permission to run the '{definition.code}' report."
        raise ApiPermissionDenied(msg)


# ─── Report metadata + data ViewSet ──────────────────────────────────────────


class ReportViewSet(viewsets.GenericViewSet):
    """
    `GET    /reports/`                  list reports the user can run
    `GET    /reports/{code}/`           one definition
    `GET    /reports/{code}/data/`      paginated table rows
    `GET    /reports/{code}/summary/`   aggregate summary
    `POST   /reports/{code}/export/`    enqueue a file generation job
    """

    permission_classes = [IsAuthenticated]
    pagination_class = StandardPagination
    lookup_field = "code"

    def list(self, request, *args, **kwargs):
        definitions = registry.allowed_for(request.user)
        ser = ReportDefinitionSerializer(definitions, many=True, context={"request": request})
        return Response(success_response(ser.data))

    def retrieve(self, request, *args, **kwargs):
        definition = registry.get(self.kwargs[self.lookup_field])
        _require_report_perm(request.user, definition)
        ser = ReportDefinitionSerializer(definition, context={"request": request})
        return Response(success_response(ser.data))

    # ── /data/ — paginated rows for the React table ──────────────────────

    @extend_schema(summary="Paginated report rows (renders the frontend table)")
    @action(detail=True, methods=["get"], url_path="data")
    def data(self, request, *args, **kwargs):
        definition = registry.get(self.kwargs[self.lookup_field])
        _require_report_perm(request.user, definition)
        params = self._validate_filters(definition, request.query_params)
        qs = definition.build_queryset(params, user=request.user)
        page = self.paginate_queryset(list(definition.iter_rows(qs, params)))
        if page is not None:
            return self.get_paginated_response(page)
        return Response(success_response(list(definition.iter_rows(qs, params))))

    # ── /summary/ — aggregate ────────────────────────────────────────────

    @extend_schema(summary="Aggregate summary for the current filters")
    @action(detail=True, methods=["get"], url_path="summary")
    def summary(self, request, *args, **kwargs):
        definition = registry.get(self.kwargs[self.lookup_field])
        _require_report_perm(request.user, definition)
        params = self._validate_filters(definition, request.query_params)
        qs = definition.build_queryset(params, user=request.user)
        return Response(success_response(definition.get_summary(qs, params)))

    # ── /export/ — enqueue the Celery task ───────────────────────────────

    @extend_schema(summary="Enqueue background file generation", request=ExportRequestSerializer)
    @action(detail=True, methods=["post"], url_path="export")
    def export(self, request, *args, **kwargs):
        definition = registry.get(self.kwargs[self.lookup_field])
        _require_report_perm(request.user, definition)

        ser = ExportRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        # Validate filters early so the user sees errors synchronously instead of
        # silently in a failed background job.
        validated_filters = self._validate_filters_dict(
            definition,
            ser.validated_data.get("filters", {}),
        )

        cap = settings.REPORT_MAX_CONCURRENT_PER_USER

        # The count check + create runs under one transaction with row locks on
        # the user's existing active jobs. Concurrent /export/ calls from the
        # same user wait on the lock so the cap is enforced consistently
        # (instead of a pure TOCTOU window between count() and create()).
        with transaction.atomic():
            active = (
                ReportJob.objects.select_for_update()
                .filter(
                    created_by=request.user,
                    status__in=ReportJob.ACTIVE_STATUSES,
                )
                .count()
            )
            if active >= cap:
                msg = (
                    f"You already have {active} active report jobs (limit {cap}). "
                    "Wait for one to finish or cancel it before queueing another."
                )
                raise BusinessRuleViolation(msg)

            job = ReportJob.objects.create(
                report_code=definition.code,
                format=ser.validated_data["format"],
                params={
                    "filters": validated_filters,
                    "include_summary": ser.validated_data.get("include_summary", False),
                },
                created_by=request.user,
                updated_by=request.user,
            )

        # Late import — keeps task autodiscover from triggering a circular import
        # when the views module is loaded during URL setup.
        from .tasks import generate_report  # noqa: PLC0415

        async_result = generate_report.delay(str(job.uuid))
        if async_result and async_result.id and not job.celery_task_id:
            ReportJob.objects.filter(pk=job.pk).update(celery_task_id=async_result.id)
            job.celery_task_id = async_result.id

        return Response(
            success_response(ReportJobSerializer(job, context={"request": request}).data),
            status=status.HTTP_202_ACCEPTED,
        )

    # ── helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _validate_filters(definition, query_params) -> dict:
        if definition.filter_serializer_class is None:
            return {}
        # Drop pagination params before validating filter serializer
        data = {k: v for k, v in query_params.items() if k not in {"page", "per_page", "format"}}
        ser = definition.filter_serializer_class(data=data)
        ser.is_valid(raise_exception=True)
        return dict(ser.validated_data)

    @staticmethod
    def _validate_filters_dict(definition, raw: dict) -> dict:
        if definition.filter_serializer_class is None:
            return {}
        ser = definition.filter_serializer_class(data=raw)
        ser.is_valid(raise_exception=True)
        # Normalize JSON-incompatible types (UUID, date, Decimal) so the resulting
        # params dict round-trips cleanly through JSONField storage.
        return _jsonify(dict(ser.validated_data))


def _jsonify(value):
    """Recursively coerce non-JSON-native values (UUID/date/datetime/Decimal) to str."""
    import datetime as _dt  # noqa: PLC0415
    import decimal as _dc  # noqa: PLC0415
    import uuid as _uuid  # noqa: PLC0415

    if isinstance(value, dict):
        return {k: _jsonify(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonify(v) for v in value]
    if isinstance(value, (_uuid.UUID, _dt.date, _dt.datetime, _dc.Decimal)):
        return str(value)
    return value


# ─── ReportJob ViewSet (status, cancel, download) ────────────────────────────


class ReportJobViewSet(
    ActionPermissionMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """
    `GET  /reports/jobs/`                       user's report jobs
    `GET  /reports/jobs/{uuid}/`                poll
    `POST /reports/jobs/{uuid}/cancel/`         revoke a running task
    `GET  /reports/jobs/{uuid}/download/?t=...` stream the file
    """

    serializer_class = ReportJobSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardPagination
    lookup_field = "uuid"
    queryset = ReportJob.objects.all()
    action_permissions = {
        "cancel": [IsAuthenticated, IsReportJobOwner],
    }

    def get_queryset(self):
        qs = ReportJob.objects.select_related("created_by").order_by("-created_at")
        user = self.request.user
        if user.is_superuser or user.has_perm("reports.view_others_reportjob"):
            return qs
        return qs.filter(created_by=user)

    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(qs)
        if page is not None:
            return self.get_paginated_response(
                ReportJobSerializer(page, many=True, context={"request": request}).data,
            )
        return Response(
            success_response(
                ReportJobSerializer(qs, many=True, context={"request": request}).data,
            ),
        )

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        return Response(
            success_response(
                ReportJobSerializer(instance, context={"request": request}).data,
            ),
        )

    # ── Cancel ───────────────────────────────────────────────────────────

    @extend_schema(summary="Revoke a queued / running report job")
    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, *args, **kwargs):
        # Lock the row so the task's final-write CAS sees status=cancelled,
        # and we don't read a stale status before deciding whether to revoke.
        with transaction.atomic():
            try:
                job = ReportJob.objects.select_for_update().get(uuid=self.kwargs["uuid"])
            except ReportJob.DoesNotExist as e:
                msg = "Report job not found."
                raise ResourceNotFound(msg) from e

            # Re-run object-level permissions on the locked row (the @action's
            # IsReportJobOwner check ran on a separately-fetched copy).
            self.check_object_permissions(request, job)

            if job.is_terminal:
                msg = f"Job is already {job.status}; nothing to cancel."
                raise BusinessRuleViolation(msg)

            celery_task_id = job.celery_task_id
            job.status = ReportJob.STATUS_CANCELLED
            job.save(update_fields=["status", "updated_at"])

        # Revoke OUTSIDE the transaction — broker calls shouldn't hold a DB lock.
        if celery_task_id:
            try:
                from config.celery import app as celery_app  # noqa: PLC0415

                celery_app.control.revoke(celery_task_id, terminate=True, signal="SIGTERM")
            except Exception:  # noqa: BLE001
                logger.warning(
                    "Could not revoke celery task %s for job %s",
                    celery_task_id,
                    job.uuid,
                    exc_info=True,
                )

        return Response(
            success_response(
                ReportJobSerializer(job, context={"request": request}).data,
                message="Report job cancelled.",
            ),
        )

    # ── Download (signed URL — token IS the authentication) ──────────────

    @extend_schema(summary="Stream the generated file (signed-token authenticated)")
    @action(
        detail=True,
        methods=["get"],
        url_path="download",
        # The signed token in `?t=` carries cryptographic proof of identity
        # (HMAC over uuid + user_id). That is the authentication for this
        # endpoint, which is why we DROP DRF's auth/permission gates — a plain
        # <a href="…?t=…"> click from the browser has no Authorization header
        # but should still download the file. Token expiry (24h) bounds the risk.
        permission_classes=[AllowAny],
        authentication_classes=[],
    )
    def download(self, request, *args, **kwargs):
        # Use `objects` (soft-delete-aware) so a job whose row was cleaned up
        # returns 404 instead of trying to open a missing file.
        job = get_object_or_404(ReportJob.objects, uuid=self.kwargs["uuid"])

        if job.status != ReportJob.STATUS_SUCCESS or not job.file:
            msg = "This report is not ready for download yet."
            raise ResourceNotFound(msg)

        token = request.query_params.get("t", "")
        if not token:
            msg = "Missing signed download token."
            raise ApiPermissionDenied(msg)
        try:
            token_user_id = verify_download_token(token, job.uuid)
        except BadSignature as e:
            msg = "Invalid or expired download token."
            raise ApiPermissionDenied(msg) from e

        # The token's encoded user_id must match the job's owner. Tokens are
        # only ever issued (by ReportJobSerializer.get_download_url) for jobs
        # the polling user could see, so the issuance side already enforced
        # access; this check guards against forged/swapped tokens.
        if token_user_id != job.created_by_id:
            msg = "Token does not match this report's owner."
            raise ApiPermissionDenied(msg)

        filename = f"{job.report_code}_{job.created_at:%Y%m%d_%H%M%S}.{job.format}"
        try:
            file_handle = job.file.open("rb")
        except (FileNotFoundError, OSError) as e:
            logger.warning(
                "ReportJob %s pointed to a missing file on disk: %s",
                job.uuid,
                job.file.name,
            )
            msg = "The report file is no longer available."
            raise ResourceNotFound(msg) from e

        response = FileResponse(file_handle, as_attachment=True, filename=filename)
        # Override content type so browsers pick the right "Save As" handler.
        if job.format == ReportJob.FORMAT_XLSX:
            response["Content-Type"] = (
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        elif job.format == ReportJob.FORMAT_PDF:
            response["Content-Type"] = "application/pdf"
        return response
