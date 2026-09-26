import asyncio
import contextlib
from datetime import UTC, datetime, timedelta

import httpx2
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

import app.main as main_module
from app.core.settings import get_settings
from app.main import app
from app.models import SnapshotRunRow, SnapshotRunStatus
from app.services.snapshot_scheduler import run_snapshot_scheduler
from app.services.snapshot_service import take_snapshot


@pytest.fixture
async def hanging_client():
    async def handler(request: httpx2.Request) -> httpx2.Response:
        # Long enough that the test always cancels while the call is pending.
        await asyncio.sleep(30)
        return httpx2.Response(500)

    async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as http_client:
        yield http_client


async def _run_rows(test_engine) -> list:
    async with test_engine.connect() as connection:
        return (
            await connection.execute(
                select(
                    SnapshotRunRow.status, SnapshotRunRow.error_code, SnapshotRunRow.finished_at
                ).order_by(SnapshotRunRow.id)
            )
        ).all()


@pytest.mark.anyio
async def test_cancelled_run_is_recorded_as_failed(
    hanging_client, settings, redis_client, test_engine
) -> None:
    task = asyncio.create_task(take_snapshot(hanging_client, settings, redis_client))
    await asyncio.sleep(0.3)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    [row] = await _run_rows(test_engine)
    assert row.status == SnapshotRunStatus.FAILED
    assert row.error_code == "cancelled"
    assert row.finished_at is not None


async def _run_scheduler_until(scheduler_args: tuple, test_engine, row_count: int) -> list:
    task = asyncio.create_task(run_snapshot_scheduler(*scheduler_args, interval_seconds=0.01))
    loop = asyncio.get_running_loop()
    deadline = loop.time() + 5
    try:
        while loop.time() < deadline:
            rows = await _run_rows(test_engine)
            finished = [row for row in rows if row.finished_at is not None]
            if len(finished) >= row_count:
                return finished[:row_count]
            await asyncio.sleep(0.01)
        raise AssertionError(f"scheduler recorded fewer than {row_count} finished runs in 5s")
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


@pytest.mark.anyio
async def test_scheduler_runs_at_once_and_keeps_polling(
    make_open_meteo_client, settings, redis_client, test_engine
) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    client = make_open_meteo_client(
        run_at=now - timedelta(hours=2), available_at=now - timedelta(hours=1)
    )

    rows = await _run_scheduler_until((client, settings, redis_client), test_engine, 3)

    assert [row.status for row in rows] == [
        SnapshotRunStatus.SUCCEEDED,
        SnapshotRunStatus.NO_NEW_DATA,
        SnapshotRunStatus.NO_NEW_DATA,
    ]


@pytest.mark.anyio
async def test_scheduler_survives_failed_passes(
    make_open_meteo_client, settings, redis_client, test_engine
) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    client = make_open_meteo_client(
        run_at=now - timedelta(hours=2), available_at=now - timedelta(hours=1), meta_status=500
    )

    rows = await _run_scheduler_until((client, settings, redis_client), test_engine, 3)

    assert {row.status for row in rows} == {SnapshotRunStatus.FAILED}
    assert {row.error_code for row in rows} == {"HTTPStatusError"}


def test_lifespan_starts_and_cancels_the_scheduler_when_enabled(monkeypatch) -> None:
    events: list[str] = []

    async def fake_scheduler(client, settings, redis, interval_seconds: float) -> None:
        events.append(f"started interval={interval_seconds}")
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            # Recording whether the shared client is already closed tells a
            # cancel from the lifespan apart from TestClient cancelling
            # leftover tasks after the lifespan has closed everything.
            events.append(f"cancelled client_closed={client.is_closed}")
            raise

    monkeypatch.setattr(main_module, "run_snapshot_scheduler", fake_scheduler)
    monkeypatch.setenv("AIRQ_SNAPSHOT_SCHEDULER_ENABLED", "true")
    monkeypatch.setenv("AIRQ_SNAPSHOT_INTERVAL_MINUTES", "2")
    get_settings.cache_clear()
    try:
        with TestClient(app):
            assert events == ["started interval=120.0"]
        assert events == ["started interval=120.0", "cancelled client_closed=False"]
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()


def test_scheduler_stays_off_in_tests() -> None:
    assert get_settings().snapshot_scheduler_enabled is False
