from datetime import UTC, datetime, timedelta

import httpx2
import pytest
from sqlalchemy import func, select

from app.models import AirReadingRow, ModelRunRow, SnapshotRunRow, SnapshotRunStatus
from app.services.snapshot_service import take_snapshot


def _now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


@pytest.mark.anyio
async def test_older_run_does_not_overwrite_readings_from_a_newer_run(
    make_open_meteo_client, settings, redis_client, test_engine
) -> None:
    now = _now()
    newer_run_at = now - timedelta(hours=2)
    older_run_at = now - timedelta(hours=14)
    newer = make_open_meteo_client(
        run_at=newer_run_at, available_at=now - timedelta(hours=1), pm2_5_offset=100.0
    )
    older = make_open_meteo_client(run_at=older_run_at, available_at=now - timedelta(hours=13))

    await take_snapshot(newer, settings, redis_client)
    await take_snapshot(older, settings, redis_client)

    async with test_engine.connect() as connection:
        rows_from_other_runs = await connection.scalar(
            select(func.count())
            .select_from(AirReadingRow)
            .where(AirReadingRow.run_at != newer_run_at)
        )
        lowest_pm2_5 = await connection.scalar(select(func.min(AirReadingRow.pm2_5)))
        model_runs = await connection.scalar(select(func.count()).select_from(ModelRunRow))

    assert rows_from_other_runs == 0
    assert lowest_pm2_5 == 101.0
    assert model_runs == 2


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("minutes_since_available", "expected_status", "expected_model_runs"),
    [(5, "not-yet-available", 0), (15, "created", 1)],
    ids=["inside-delay", "past-delay"],
)
async def test_run_is_recorded_only_after_the_availability_delay(
    make_open_meteo_client,
    settings,
    redis_client,
    test_engine,
    minutes_since_available: int,
    expected_status: str,
    expected_model_runs: int,
) -> None:
    now = _now()
    client = make_open_meteo_client(
        run_at=now - timedelta(hours=1),
        available_at=now - timedelta(minutes=minutes_since_available),
    )
    delayed_settings = settings.model_copy(update={"snapshot_min_available_delay_minutes": 10})

    result = await take_snapshot(client, delayed_settings, redis_client)

    async with test_engine.connect() as connection:
        model_runs = await connection.scalar(select(func.count()).select_from(ModelRunRow))
    assert result.status == expected_status
    assert model_runs == expected_model_runs


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("meta_status", "hourly_status"),
    [(500, 200), (200, 500)],
    ids=["meta-fails", "hourly-fails"],
)
async def test_failed_upstream_marks_run_failed_and_does_not_block_the_next_run(
    make_open_meteo_client,
    settings,
    redis_client,
    test_engine,
    meta_status: int,
    hourly_status: int,
) -> None:
    now = _now()
    run_times = {"run_at": now - timedelta(hours=2), "available_at": now - timedelta(hours=1)}
    failing = make_open_meteo_client(
        **run_times, meta_status=meta_status, hourly_status=hourly_status
    )

    with pytest.raises(httpx2.HTTPStatusError):
        await take_snapshot(failing, settings, redis_client)

    async with test_engine.connect() as connection:
        run_log = (
            await connection.execute(select(SnapshotRunRow.status, SnapshotRunRow.error_code))
        ).one()
        model_runs = await connection.scalar(select(func.count()).select_from(ModelRunRow))
    assert run_log.status == SnapshotRunStatus.FAILED
    assert run_log.error_code == "HTTPStatusError"
    assert model_runs == 0

    result = await take_snapshot(make_open_meteo_client(**run_times), settings, redis_client)
    assert result.status == "created"
