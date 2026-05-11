import logging
import time
from concurrent.futures import ThreadPoolExecutor

from django.db import connections
from django.utils.deprecation import MiddlewareMixin
from ipware import get_client_ip

from pms_api.core.models.access_log import AccessLog

logger = logging.getLogger(__name__)

# Single background worker — every request that needs to write an AccessLog
# row submits the work here so the response can return immediately. One worker
# is enough since rows are small and inserts are fast; raise max_workers if
# the queue ever backs up under load.
_access_log_executor = ThreadPoolExecutor(
    max_workers=2,
    thread_name_prefix="access-log",
)


def _write_access_log(payload):
    try:
        AccessLog.objects.create(**payload)
    except Exception:
        logger.exception("Failed to persist AccessLog entry")
    finally:
        # Worker threads get their own DB connection — release it so it doesn't
        # linger past CONN_MAX_AGE without anyone polling for health.
        connections.close_all()


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
        raw = getattr(request, "data", None)
        if isinstance(raw, dict):
            body = {k: "***" if k.lower() in self.SENSITIVE_KEYS else v for k, v in raw.items()}

        payload = {
            "user": request.user,
            "method": request.method,
            "endpoint": request.path,
            "ip_address": ip,
            "user_agent": request.headers.get("user-agent", "")[:512],
            "request_body": body,
            "response_status": response.status_code,
            "duration_ms": duration,
            "session_key": getattr(request.session, "session_key", "") or "",
        }
        _access_log_executor.submit(_write_access_log, payload)

        return response
