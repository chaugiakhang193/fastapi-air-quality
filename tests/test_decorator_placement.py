import logging

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from app.core.timing import log_duration


def _correct_order_app() -> FastAPI:
    probe_app = FastAPI()
    router = APIRouter()

    @router.get("/correct")
    @log_duration
    async def correct() -> dict[str, str]:
        return {"ok": "yes"}

    probe_app.include_router(router)
    return probe_app


def _wrong_order_app() -> FastAPI:
    probe_app = FastAPI()
    router = APIRouter()

    @log_duration
    @router.get("/wrong")
    async def wrong() -> dict[str, str]:
        return {"ok": "yes"}

    probe_app.include_router(router)
    return probe_app


def test_decorator_below_router_get_runs(caplog) -> None:
    with caplog.at_level(logging.INFO, logger="airq.timing"):
        response = TestClient(_correct_order_app()).get("/correct")

    assert response.status_code == 200
    assert any("took" in record.message for record in caplog.records)


def test_decorator_above_router_get_never_runs(caplog) -> None:
    with caplog.at_level(logging.INFO, logger="airq.timing"):
        response = TestClient(_wrong_order_app()).get("/wrong")

    assert response.status_code == 200
    # router.get() already captured a reference to the undecorated function
    # (decorators apply bottom-up); wrapping it afterwards only rebinds a
    # local name that nothing looks up again.
    assert not any("took" in record.message for record in caplog.records)
