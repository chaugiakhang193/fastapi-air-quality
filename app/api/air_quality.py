from datetime import date

import httpx2
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.open_meteo import fetch_hourly
from app.core.db import get_session
from app.core.envelope import EnvelopeRoute
from app.core.settings import Settings, get_settings
from app.repositories.locations import get_location_by_code
from app.schemas.location import Location

router = APIRouter(prefix="/air-quality", tags=["air-quality"], route_class=EnvelopeRoute)


def get_http_client(request: Request) -> httpx2.AsyncClient:
    # Created once in main.py's lifespan so every request reuses one connection pool.
    return request.app.state.http_client


async def parse_locations(locations: str, session: AsyncSession) -> list[Location]:
    codes = [code.strip() for code in locations.split(",") if code.strip()]
    if not codes:
        raise HTTPException(status_code=422, detail="Locations must contain at least one code")

    resolved: list[Location] = []
    for code in codes:
        row = await get_location_by_code(session, code)
        if row is None:
            raise HTTPException(status_code=404, detail=f"Unknown location code: {code}")
        resolved.append(
            Location(
                code=row.code,
                name=row.name,
                latitude=row.latitude,
                longitude=row.longitude,
                timezone=row.timezone,
            )
        )
    return resolved


@router.get("/hourly")
async def get_hourly(
    Locations: str,
    client: httpx2.AsyncClient = Depends(get_http_client),
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    locations = await parse_locations(Locations, session)
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
    return [
        {"Code": location.code, "Name": location.name, "Hourly": result["hourly"]}
        for location, result in zip(locations, results, strict=True)
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
    Locations: str,
    From: date,
    To: date,
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    codes = [code.strip() for code in Locations.split(",") if code.strip()]
    if not codes:
        raise HTTPException(status_code=422, detail="Locations must not be blank")
    if From > To:
        raise HTTPException(status_code=422, detail="From must not be after To")

    rows = (
        await session.execute(
            _DAILY_SQL,
            {
                "location_codes": codes,
                "date_from": From,
                "date_to": To,
                "min_hours": MIN_HOURS_PER_DAY,
                "who_pm2_5": WHO_PM2_5_24H_UG_M3,
                "who_pm10": WHO_PM10_24H_UG_M3,
            },
        )
    ).all()

    by_location: dict[str, dict] = {}
    for row in rows:
        entry = by_location.setdefault(
            row.location_code,
            {"Code": row.location_code, "Name": row.location_name, "Days": []},
        )
        entry["Days"].append(
            {
                "Date": row.local_date.isoformat(),
                "HoursCount": row.hours_count,
                "ForecastHours": row.forecast_hours,
                "AvgPm2_5": row.avg_pm2_5,
                "AvgPm10": row.avg_pm10,
                "AvgUsAqi": row.avg_us_aqi,
                "AvgEuropeanAqi": row.avg_european_aqi,
                "ExceedsWhoPm2_5": row.exceeds_who_pm2_5,
                "ExceedsWhoPm10": row.exceeds_who_pm10,
            }
        )
    return list(by_location.values())
