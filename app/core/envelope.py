import json
import logging

from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger("airq.envelope")

DEFAULT_ERROR_CODES: dict[int, str] = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    422: "VALIDATION_ERROR",
    500: "INTERNAL_ERROR",
    502: "UPSTREAM_ERROR",
    503: "UPSTREAM_UNAVAILABLE",
}


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def error_response(
    request: Request,
    status_code: int,
    message: str,
    code: str | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    resolved_code = code or DEFAULT_ERROR_CODES.get(status_code, "ERROR")
    return JSONResponse(
        status_code=status_code,
        content={
            "Data": None,
            "Error": {"Code": resolved_code, "Message": message},
            "RequestId": _request_id(request),
        },
        headers=headers,
    )


def http_exception_to_response(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    if isinstance(exc.detail, dict) and "code" in exc.detail:
        return error_response(
            request,
            exc.status_code,
            str(exc.detail.get("message", "")),
            code=exc.detail["code"],
            headers=dict(exc.headers) if exc.headers else None,
        )
    return error_response(
        request,
        exc.status_code,
        str(exc.detail),
        headers=dict(exc.headers) if exc.headers else None,
    )


class EnvelopeRoute(APIRoute):
    def get_route_handler(self):
        original_route_handler = super().get_route_handler()

        async def envelope_route_handler(request: Request) -> Response:
            try:
                response = await original_route_handler(request)
            except RequestValidationError as exc:
                return error_response(request, 422, str(exc.errors()))
            except StarletteHTTPException as exc:
                return http_exception_to_response(request, exc)
            except Exception:
                logger.exception(
                    "request_id=%s unhandled error in %s", _request_id(request), request.url.path
                )
                return error_response(request, 500, "Internal server error")

            data = json.loads(response.body) if response.body else None
            return JSONResponse(
                status_code=response.status_code,
                content={"Data": data, "Error": None, "RequestId": _request_id(request)},
            )

        return envelope_route_handler
