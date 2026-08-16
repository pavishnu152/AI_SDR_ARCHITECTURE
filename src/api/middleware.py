"""
Request-ID middleware.

Assigns a unique request_id to every incoming HTTP request (or reuses an
inbound `X-Request-ID` header, so an upstream gateway/load balancer's ID
can be preserved end to end), stores it in the request_id contextvar
(src/core/logging.py) for the duration of the request, and echoes it back
in the response header. This is a standard production pattern for tracing
one request across distributed logs — here it's a single process, but the
same mechanism is what lets you find every log line (across all 4 agents
in a pipeline run) belonging to one specific POST /leads call.
"""
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from src.core.logging import request_id_var


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        token = request_id_var.set(request_id)
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers["X-Request-ID"] = request_id
        return response
