from datetime import UTC, datetime

import pytest
from sqlalchemy import delete, select

from app.models import AirReadingRow, LocationRow, ModelRunRow
from app.services.snapshot_service import _to_utc


@pytest.mark.parametrize(
    ("local_iso", "timezone", "expected_utc"),
    [
        ("2026-09-18T00:00", "Asia/Ho_Chi_Minh", datetime(2026, 9, 17, 17, tzinfo=UTC)),
        ("2026-09-18T00:00", "Asia/Kolkata", datetime(2026, 9, 17, 18, 30, tzinfo=UTC)),
        ("2026-09-17T23:00", "Asia/Kolkata", datetime(2026, 9, 17, 17, 30, tzinfo=UTC)),
    ],
    ids=["hanoi-midnight", "new-delhi-midnight", "new-delhi-23h"],
)
def test_to_utc_uses_the_location_timezone(
    local_iso: str, timezone: str, expected_utc: datetime
) -> None:
    assert _to_utc(local_iso, timezone) == expected_utc


@pytest.fixture
async def new_delhi(db_session):
    location = LocationRow(
        code="newdelhi",
        name="New Delhi",
        latitude=28.6139,
        longitude=77.209,
        timezone="Asia/Kolkata",
    )
    db_session.add(location)
    await db_session.commit()
    yield location
    await db_session.execute(delete(AirReadingRow).where(AirReadingRow.location_id == location.id))
    await db_session.delete(location)
    await db_session.commit()


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("code", "local_iso", "expected_local_date"),
    [
        ("hanoi", "2026-09-17T23:00", "2026-09-17"),
        ("hanoi", "2026-09-18T00:00", "2026-09-18"),
        ("newdelhi", "2026-09-17T23:00", "2026-09-17"),
        ("newdelhi", "2026-09-18T00:00", "2026-09-18"),
    ],
    ids=["hanoi-23h", "hanoi-00h", "new-delhi-23h", "new-delhi-00h"],
)
async def test_reading_is_grouped_under_its_local_date(
    db_session, api_client, new_delhi, code: str, local_iso: str, expected_local_date: str
) -> None:
    location = await db_session.scalar(select(LocationRow).where(LocationRow.code == code))
    run_at = datetime(2026, 9, 17, tzinfo=UTC)
    model_run = ModelRunRow(
        model="cams_global",
        run_at=run_at,
        available_at=run_at,
        first_seen_at=run_at,
        last_checked_at=run_at,
    )
    db_session.add(model_run)
    await db_session.flush()
    db_session.add(
        AirReadingRow(
            location_id=location.id,
            observed_at=_to_utc(local_iso, location.timezone),
            pm2_5=20.0,
            pm10=30.0,
            us_aqi=60,
            european_aqi=40,
            model_run_id=model_run.id,
            run_at=run_at,
        )
    )
    await db_session.commit()

    response = await api_client.get(
        "/air-quality/daily",
        params={"Locations": code, "From": "2026-09-16", "To": "2026-09-19"},
    )

    assert response.status_code == 200
    days = response.json()["Data"][0]["Days"]
    assert [day["Date"] for day in days] == [expected_local_date]
    assert days[0]["HoursCount"] == 1
