from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx2
from fastapi import FastAPI

from app.api.air_quality import router as air_quality_router
from app.api.locations import router as locations_router
from app.core.logging import configure_logging
from app.core.middleware import RequestIdMiddleware, TimingMiddleware
from app.core.settings import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    settings = get_settings()
    app.state.http_client = httpx2.AsyncClient(timeout=settings.open_meteo_timeout_seconds)
    try:
        yield
    finally:
        # try/finally so the client is still closed if something throws the
        # exception back into this generator during shutdown.
        await app.state.http_client.aclose()


app = FastAPI(title="fastapi-air-quality", lifespan=lifespan)

# Registered last, so Starlette makes it the outermost layer and it runs
# before TimingMiddleware on the way in (the last add_middleware() call ends
# up outermost). RequestIdMiddleware must be outermost so request_id already
# exists by the time TimingMiddleware logs its "done" line — see
# tests/test_middleware_order.py for the ordering proof.
app.add_middleware(TimingMiddleware)
app.add_middleware(RequestIdMiddleware)

app.include_router(locations_router)
app.include_router(air_quality_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
