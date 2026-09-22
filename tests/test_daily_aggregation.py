from datetime import UTC, datetime, timedelta

import httpx2
import pytest
from sqlalchemy import select

from app.main import app
from app.models import AirReadingRow, LocationRow, ModelRunRow


async def _seed_day(db_session, hours: int, run_at: datetime) -> None:
    location = await db_session.scalar(select(LocationRow).where(LocationRow.code == "hanoi"))
    model_run = ModelRunRow(
        model="cams_global",
        run_at=run_at,
        available_at=run_at,
        first_seen_at=run_at,
        last_checked_at=run_at,
    )
    db_session.add(model_run)
    await db_session.flush()

    for hour in range(hours):
        db_session.add(
            AirReadingRow(
                location_id=location.id,
                observed_at=datetime(2026, 9, 17, 17, tzinfo=UTC) + timedelta(hours=hour),
                pm2_5=50.0,
                pm10=60.0,
                us_aqi=120,
                european_aqi=70,
                model_run_id=model_run.id,
                run_at=run_at,
            )
        )
    await db_session.commit()


async def _get_day() -> dict:
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/air-quality/daily",
            params={"Locations": "hanoi", "From": "2026-09-18", "To": "2026-09-18"},
        )
    assert response.status_code == 200
    return response.json()[0]["Days"][0]


@pytest.mark.anyio
async def test_day_below_min_hours_returns_null_averages(db_session):
    await _seed_day(db_session, 10, datetime(2026, 9, 18, tzinfo=UTC))
    day = await _get_day()

    assert day["HoursCount"] == 10
    assert day["AvgPm2_5"] is None
    assert day["ExceedsWhoPm2_5"] is None


@pytest.mark.anyio
async def test_complete_day_returns_averages_and_forecast_hours(db_session):
    await _seed_day(db_session, 24, datetime(2026, 9, 18, 5, tzinfo=UTC))
    day = await _get_day()

    assert day["HoursCount"] == 24
    assert day["ForecastHours"] == 12
    assert day["AvgPm2_5"] == 50.0
    assert day["AvgPm10"] == 60.0
    assert day["ExceedsWhoPm2_5"] is True
    assert day["ExceedsWhoPm10"] is True
