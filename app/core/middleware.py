import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("airq.middleware")


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request.state.request_id = uuid.uuid4().hex[:8]
        logger.info(
            "request_id=%s request-id:enter %s %s",
            request.state.request_id,
            request.method,
            request.url.path,
        )
        response = await call_next(request)
        logger.info("request_id=%s request-id:exit", request.state.request_id)
        return response


class TimingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # call_next() returns as soon as the response leaves the router — any
        # dependency teardown that runs after `yield` happens AFTER this
        # elapsed_ms is computed, not inside it. See
        # tests/test_yield_teardown_order.py: "middleware:after-call-next"
        # is logged before "dependency:after-yield".
        logger.info("timing:enter")
        started_at = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - started_at) * 1000
        request_id = getattr(request.state, "request_id", "-")
        logger.info("request_id=%s timing:exit done in %.1fms", request_id, elapsed_ms)
        return response
