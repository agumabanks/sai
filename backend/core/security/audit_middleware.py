"""
Audit Middleware — logs every HTTP request to the audit_log table.

Captures:
  - Actor (session user or API key identity)
  - Action (HTTP method + path)
  - IP address and User-Agent
  - Request success/failure
  - Response time
"""

import time
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

# Paths to skip auditing (health checks, static assets)
SKIP_PATHS = {
    "/health",
    "/favicon.ico",
    "/static",
    "/docs",
    "/openapi.json",
    "/redoc",
}


class AuditMiddleware(BaseHTTPMiddleware):
    """Starlette middleware that audit-logs every request."""

    async def dispatch(self, request: Request, call_next) -> Response:
        # Skip non-auditable paths
        if any(request.url.path.startswith(p) for p in SKIP_PATHS):
            return await call_next(request)

        start = time.monotonic()
        actor = self._get_actor(request)
        action = f"{request.method} {request.url.path}"

        # Process the request
        response: Response = None
        success = True
        error_detail = ""

        try:
            response = await call_next(request)
            success = 200 <= response.status_code < 400
            if not success:
                error_detail = f"HTTP {response.status_code}"
        except Exception as e:
            success = False
            error_detail = str(e)[:200]
            raise
        finally:
            elapsed_ms = int((time.monotonic() - start) * 1000)

            # Async audit log (fire-and-forget, don't block response)
            try:
                from core.database import AuditLog

                await AuditLog.log(
                    actor=actor,
                    action=action,
                    resource=str(request.url)[:200],
                    details={
                        "ip": self._get_ip(request),
                        "user_agent": request.headers.get("user-agent", "?")[:200],
                        "elapsed_ms": elapsed_ms,
                        "error": error_detail or None,
                    },
                    success=success,
                )
            except Exception as log_err:
                # Never let audit logging crash the request
                logger.debug(f"Audit log failed: {log_err}")

        return response

    def _get_actor(self, request: Request) -> str:
        """Extract actor identity from the request."""
        # Try session
        session = request.session if hasattr(request, "session") else {}
        if isinstance(session, dict):
            user = session.get("user")
            if user:
                return user.get("email", user.get("id", "session_user"))

        # Try Authorization header
        auth = request.headers.get("authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
            return f"api_key:{token[:8]}..."

        return f"anon:{self._get_ip(request)}"

    def _get_ip(self, request: Request) -> str:
        """Get client IP, handling reverse proxies."""
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"
