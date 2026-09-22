from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx2
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.open_meteo import fetch_hourly, fetch_meta
from app.core.db import async_session_factory
from app.core.settings import Settings
from app.models import (
    AirReadingRow,
    LocationRow,
    ModelRunRow,
    SnapshotRow,
    SnapshotRunRow,
    SnapshotRunStatus,
)


class SnapshotLockHeldError(Exception):
    """Another snapshot run already holds the advisory lock."""


@dataclass
class SnapshotResult:
    status: str
    run_at: datetime | None
    locations_fetched: int


async def take_snapshot(client: httpx2.AsyncClient, settings: Settings) -> SnapshotResult:
    run_log_id = await _start_run_log()
    model_run_id: int | None = None
    try:
        async with async_session_factory() as session, session.begin():
            # hashtext() derives the lock key from this label instead of a bare
            # int, so the key is self-explanatory and any other advisory lock
            # added later just needs its own distinct label to avoid colliding
            # (all advisory locks in a Postgres database share one key space).
            lock_acquired = (
                await session.execute(
                    text("SELECT pg_try_advisory_xact_lock(hashtext(:lock_name))"),
                    {"lock_name": "take_snapshot"},
                )
            ).scalar_one()
            if not lock_acquired:
                raise SnapshotLockHeldError
            result, model_run_id = await _run_snapshot_locked(session, client, settings)
        status = (
            SnapshotRunStatus.SUCCEEDED
            if result.status == "created"
            else SnapshotRunStatus.NO_NEW_DATA
        )
        await _finish_run_log(run_log_id, status, model_run_id=model_run_id)
        return result
    except SnapshotLockHeldError:
        await _finish_run_log(run_log_id, SnapshotRunStatus.FAILED, error_code="lock_held")
        raise
    except Exception as exc:
        await _finish_run_log(
            run_log_id,
            SnapshotRunStatus.FAILED,
            error_code=type(exc).__name__,
            error_detail=str(exc),
        )
        raise


async def _run_snapshot_locked(
    session: AsyncSession,
    client: httpx2.AsyncClient,
    settings: Settings,
) -> tuple[SnapshotResult, int | None]:
    meta = await fetch_meta(client, settings.open_meteo_meta_url)
    now = datetime.now(UTC)
    available_cutoff = meta.available_at + timedelta(
        minutes=settings.snapshot_min_available_delay_minutes
    )
    if now < available_cutoff:
        return SnapshotResult("not-yet-available", None, 0), None

    existing = await session.scalar(
        select(ModelRunRow).where(
            ModelRunRow.model == settings.open_meteo_model,
            ModelRunRow.run_at == meta.run_at,
        )
    )
    if existing is not None:
        existing.check_count += 1
        existing.last_checked_at = now
        return SnapshotResult("unchanged", existing.run_at, 0), existing.id

    locations = list((await session.scalars(select(LocationRow).order_by(LocationRow.id))).all())
    past_days = await _resolve_past_days(session, settings)
    results = await fetch_hourly(
        client,
        settings.open_meteo_air_quality_url,
        locations,
        past_days=past_days,
    )

    model_run = ModelRunRow(
        model=settings.open_meteo_model,
        run_at=meta.run_at,
        available_at=meta.available_at,
        first_seen_at=now,
        last_checked_at=now,
        check_count=1,
    )
    session.add(model_run)
    await session.flush()

    for location, payload in zip(locations, results, strict=True):
        session.add(
            SnapshotRow(
                model_run_id=model_run.id,
                location_id=location.id,
                fetched_at=now,
                payload=payload,
            )
        )
        await _upsert_air_readings(session, location, payload, model_run)

    return SnapshotResult("created", model_run.run_at, len(locations)), model_run.id


async def _resolve_past_days(session: AsyncSession, settings: Settings) -> int:
    latest_run_at = await session.scalar(select(func.max(ModelRunRow.run_at)))
    if latest_run_at is None:
        return settings.snapshot_max_past_days
    days_since = (datetime.now(UTC) - latest_run_at).days + 1
    return max(1, min(settings.snapshot_max_past_days, days_since))


async def _upsert_air_readings(
    session: AsyncSession,
    location: LocationRow,
    payload: dict,
    model_run: ModelRunRow,
) -> None:
    hourly = payload["hourly"]
    rows = [
        {
            "location_id": location.id,
            "observed_at": _to_utc(time_str, location.timezone),
            "pm2_5": pm2_5,
            "pm10": pm10,
            "us_aqi": us_aqi,
            "european_aqi": european_aqi,
            "model_run_id": model_run.id,
            "run_at": model_run.run_at,
        }
        for time_str, pm2_5, pm10, us_aqi, european_aqi in zip(
            hourly["time"],
            hourly["pm2_5"],
            hourly["pm10"],
            hourly["us_aqi"],
            hourly["european_aqi"],
            strict=True,
        )
    ]
    if not rows:
        return
    stmt = pg_insert(AirReadingRow).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=[AirReadingRow.location_id, AirReadingRow.observed_at],
        set_={
            "pm2_5": stmt.excluded.pm2_5,
            "pm10": stmt.excluded.pm10,
            "us_aqi": stmt.excluded.us_aqi,
            "european_aqi": stmt.excluded.european_aqi,
            "model_run_id": stmt.excluded.model_run_id,
            "run_at": stmt.excluded.run_at,
        },
        where=stmt.excluded.run_at > AirReadingRow.run_at,
    )
    await session.execute(stmt)


def _to_utc(local_iso: str, timezone: str) -> datetime:
    return datetime.fromisoformat(local_iso).replace(tzinfo=ZoneInfo(timezone)).astimezone(UTC)


async def _start_run_log() -> int:
    # A separate committed transaction preserves the attempt if the snapshot transaction rolls back.
    async with async_session_factory() as session:
        run_log = SnapshotRunRow(started_at=datetime.now(UTC), status=SnapshotRunStatus.RUNNING)
        session.add(run_log)
        await session.commit()
        return run_log.id


async def _finish_run_log(
    run_log_id: int,
    status: SnapshotRunStatus,
    model_run_id: int | None = None,
    error_code: str | None = None,
    error_detail: str | None = None,
) -> None:
    async with async_session_factory() as session:
        run_log = await session.get(SnapshotRunRow, run_log_id)
        if run_log is None:
            return
        run_log.finished_at = datetime.now(UTC)
        run_log.status = status
        run_log.model_run_id = model_run_id
        run_log.error_code = error_code
        run_log.error_detail = error_detail
        await session.commit()
