import json
import logging
import time

from django.utils.deprecation import MiddlewareMixin
from ipware import get_client_ip

from pms_api.core.models.access_log import AccessLog

logger = logging.getLogger(__name__)


class AccessLogMiddleware(MiddlewareMixin):
    TRACKED_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
    SENSITIVE_KEYS = {"password", "token", "secret", "authorization"}

    def process_request(self, request):
        request.start_time = time.time()

    def process_response(self, request, response):
        if request.method not in self.TRACKED_METHODS:
            return response

        if not hasattr(request, "user") or not request.user.is_authenticated:
            return response

        ip, _ = get_client_ip(request)

        duration = int(
            (time.time() - getattr(request, "start_time", time.time())) * 1000,
        )

        body = None
        try:
            if request.body:
                raw = json.loads(request.body)
                body = {
                    k: "***" if k.lower() in self.SENSITIVE_KEYS else v
                    for k, v in raw.items()
                }
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            logger.debug("Failed to parse request body: %s", exc)

        AccessLog.objects.create(
            user=request.user,
            method=request.method,
            endpoint=request.path,
            ip_address=ip,
            user_agent=request.headers.get("user-agent", "")[:512],
            request_body=body,
            response_status=response.status_code,
            duration_ms=duration,
            session_key=request.session.session_key or "",
        )

        return response
