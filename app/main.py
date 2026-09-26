import asyncio
import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx2
from fastapi import APIRouter, FastAPI, Request
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.air_quality import router as air_quality_router
from app.api.locations import router as locations_router
from app.api.snapshots import router as snapshots_router
from app.core.db import engine
from app.core.envelope import EnvelopeRoute, http_exception_to_response
from app.core.logging import configure_logging
from app.core.middleware import RequestIdMiddleware, TimingMiddleware
from app.core.redis import create_redis
from app.core.settings import get_settings
from app.services.snapshot_scheduler import run_snapshot_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    settings = get_settings()
    app.state.http_client = httpx2.AsyncClient(timeout=settings.open_meteo_timeout_seconds)
    app.state.redis = create_redis(settings)
    scheduler: asyncio.Task[None] | None = None
    if settings.snapshot_scheduler_enabled:
        scheduler = asyncio.create_task(
            run_snapshot_scheduler(
                app.state.http_client,
                settings,
                app.state.redis,
                interval_seconds=settings.snapshot_interval_minutes * 60,
            )
        )
    try:
        yield
    finally:
        # The scheduler stops first: a pass still running when the clients
        # below close would fail on a closed client instead of being cancelled.
        if scheduler is not None:
            scheduler.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await scheduler
        # try/finally so the clients are still closed if something throws the
        # exception back into this generator during shutdown.
        await app.state.http_client.aclose()
        await app.state.redis.aclose()
        await engine.dispose()


app = FastAPI(title="fastapi-air-quality", lifespan=lifespan)


@app.exception_handler(StarletteHTTPException)
async def starlette_http_exception_handler(request: Request, exc: StarletteHTTPException):
    # Covers requests that never matched any route (true 404) or matched the
    # path with the wrong method (405) — these never reach an EnvelopeRoute
    # handler, since no APIRoute ever runs for them.
    return http_exception_to_response(request, exc)


# Registered last, so Starlette makes it the outermost layer and it runs
# before TimingMiddleware on the way in (the last add_middleware() call ends
# up outermost). RequestIdMiddleware must be outermost so request_id already
# exists by the time TimingMiddleware logs its "done" line — see
# tests/test_middleware_order.py for the ordering proof.
app.add_middleware(TimingMiddleware)
app.add_middleware(RequestIdMiddleware)

app.include_router(locations_router)
app.include_router(air_quality_router)
app.include_router(snapshots_router)

# FastAPI() does not forward route_class to its own internal router (checked
# against fastapi/applications.py: routing.APIRouter(...) is built without a
# route_class argument), so /health needs its own APIRouter to get the same
# envelope wrapping as every other route.
health_router = APIRouter(route_class=EnvelopeRoute)


@health_router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(health_router)
