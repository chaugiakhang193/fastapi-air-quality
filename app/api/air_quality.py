import logging
from datetime import date

import httpx2
from fastapi import APIRouter, Depends, HTTPException, Request
from redis.asyncio import Redis
from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.open_meteo import fetch_hourly
from app.core.db import get_session
from app.core.envelope import EnvelopeRoute
from app.core.redis import get_redis
from app.core.settings import Settings, get_settings
from app.repositories.locations import get_location_by_code
from app.schemas.air_quality import (
    DailyEntry,
    HourlyReading,
    LocationCodes,
    LocationDaily,
    LocationHourly,
)
from app.schemas.location import Location
from app.services.daily_cache import daily_cache_key, read_daily, write_daily

logger = logging.getLogger("airq.cache")

router = APIRouter(prefix="/air-quality", tags=["air-quality"], route_class=EnvelopeRoute)


def get_http_client(request: Request) -> httpx2.AsyncClient:
    # Created once in main.py's lifespan so every request reuses one connection pool.
    return request.app.state.http_client


async def resolve_locations(codes: list[str], session: AsyncSession) -> list[Location]:
    resolved: list[Location] = []
    for code in codes:
        row = await get_location_by_code(session, code)
        if row is None:
            raise HTTPException(status_code=404, detail=f"Unknown location code: {code}")
        resolved.append(Location.model_validate(row))
    return resolved


@router.get("/hourly")
async def get_hourly(
    Locations: LocationCodes,
    client: httpx2.AsyncClient = Depends(get_http_client),
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
) -> list[LocationHourly]:
    locations = await resolve_locations(Locations, session)
    try:
        results = await fetch_hourly(client, settings.open_meteo_air_quality_url, locations)
    except httpx2.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "code": "UPSTREAM_ERROR",
                "message": f"Open-Meteo returned {exc.response.status_code}",
            },
        ) from exc
    except httpx2.RequestError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "UPSTREAM_UNAVAILABLE", "message": "Could not reach Open-Meteo"},
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=502, detail={"code": "UPSTREAM_ERROR", "message": str(exc)}
        ) from exc
    try:
        return [
            LocationHourly(
                code=location.code,
                name=location.name,
                hourly=_rows_from_parallel_arrays(result["hourly"]),
            )
            for location, result in zip(locations, results, strict=True)
        ]
    except ValueError as exc:
        # Covers both zip(strict=True) on arrays of unequal length and
        # pydantic.ValidationError (a ValueError subclass) on wrongly typed
        # values. The message stays generic because str(exc) would expose
        # internal details such as zip argument positions.
        raise HTTPException(
            status_code=502,
            detail={
                "code": "UPSTREAM_ERROR",
                "message": "Open-Meteo returned malformed hourly data",
            },
        ) from exc


def _rows_from_parallel_arrays(hourly: dict) -> list[HourlyReading]:
    # Open-Meteo returns parallel arrays (one list per metric, same length,
    # matched by index) — turned into one HourlyReading row per hour here so
    # the response is a normal list of objects instead of that shape.
    return [
        HourlyReading(
            time=time,
            pm2_5=pm2_5,
            pm10=pm10,
            us_aqi=us_aqi,
            european_aqi=european_aqi,
        )
        for time, pm2_5, pm10, us_aqi, european_aqi in zip(
            hourly["time"],
            hourly["pm2_5"],
            hourly["pm10"],
            hourly["us_aqi"],
            hourly["european_aqi"],
            strict=True,
        )
    ]


WHO_PM2_5_24H_UG_M3 = 15.0
WHO_PM10_24H_UG_M3 = 45.0
MIN_HOURS_PER_DAY = 18

_DAILY_SQL = text(
    """
    SELECT
        l.code AS location_code,
        l.name AS location_name,
        (ar.observed_at AT TIME ZONE l.timezone)::date AS local_date,
        COUNT(ar.pm2_5) AS hours_count,
        COUNT(*) FILTER (WHERE ar.observed_at >= ar.run_at) AS forecast_hours,
        CASE WHEN COUNT(ar.pm2_5) >= :min_hours THEN AVG(ar.pm2_5) END AS avg_pm2_5,
        CASE WHEN COUNT(ar.pm2_5) >= :min_hours THEN AVG(ar.pm10) END AS avg_pm10,
        CASE WHEN COUNT(ar.pm2_5) >= :min_hours THEN AVG(ar.us_aqi) END AS avg_us_aqi,
        CASE WHEN COUNT(ar.pm2_5) >= :min_hours THEN AVG(ar.european_aqi) END AS avg_european_aqi,
        CASE WHEN COUNT(ar.pm2_5) >= :min_hours
             THEN AVG(ar.pm2_5) > :who_pm2_5 END AS exceeds_who_pm2_5,
        CASE WHEN COUNT(ar.pm2_5) >= :min_hours
             THEN AVG(ar.pm10) > :who_pm10 END AS exceeds_who_pm10
    FROM air_reading ar
    JOIN location l ON l.id = ar.location_id
    WHERE l.code IN :location_codes
      AND (ar.observed_at AT TIME ZONE l.timezone)::date BETWEEN :date_from AND :date_to
    GROUP BY l.code, l.name, local_date
    ORDER BY l.code, local_date
    """
).bindparams(bindparam("location_codes", expanding=True))


@router.get("/daily")
async def get_daily(
    Locations: LocationCodes,
    From: date,
    To: date,
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
    settings: Settings = Depends(get_settings),
) -> list[LocationDaily]:
    if From > To:
        raise HTTPException(status_code=422, detail="From must not be after To")

    cache_key = daily_cache_key(Locations, From, To)
    cached = await read_daily(redis, cache_key)
    if cached is not None:
        logger.info("daily cache hit key=%s", cache_key)
        return cached
    logger.info("daily cache miss key=%s", cache_key)

    rows = (
        await session.execute(
            _DAILY_SQL,
            {
                "location_codes": Locations,
                "date_from": From,
                "date_to": To,
                "min_hours": MIN_HOURS_PER_DAY,
                "who_pm2_5": WHO_PM2_5_24H_UG_M3,
                "who_pm10": WHO_PM10_24H_UG_M3,
            },
        )
    ).all()

    by_location: dict[str, LocationDaily] = {}
    for row in rows:
        entry = by_location.setdefault(
            row.location_code,
            LocationDaily(code=row.location_code, name=row.location_name, days=[]),
        )
        entry.days.append(
            DailyEntry(
                date=row.local_date.isoformat(),
                hours_count=row.hours_count,
                forecast_hours=row.forecast_hours,
                avg_pm2_5=row.avg_pm2_5,
                avg_pm10=row.avg_pm10,
                avg_us_aqi=row.avg_us_aqi,
                avg_european_aqi=row.avg_european_aqi,
                exceeds_who_pm2_5=row.exceeds_who_pm2_5,
                exceeds_who_pm10=row.exceeds_who_pm10,
            )
        )
    daily = list(by_location.values())
    await write_daily(redis, cache_key, daily, settings.daily_cache_ttl_seconds)
    return daily
