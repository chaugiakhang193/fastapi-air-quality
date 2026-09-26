import json
from datetime import UTC, date, datetime, timedelta

import pytest
from redis.asyncio import Redis
from sqlalchemy import delete

from app.core.redis import get_redis
from app.main import app
from app.models import AirReadingRow
from app.services.daily_cache import DAILY_KEY_PREFIX, daily_cache_key
from app.services.snapshot_service import take_snapshot

DAY_PARAMS = {"Locations": "hanoi", "From": "2026-09-18", "To": "2026-09-18"}


def _now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


async def _daily_keys(redis_client) -> list[str]:
    return [key async for key in redis_client.scan_iter(match=f"{DAILY_KEY_PREFIX}*")]


async def _hanoi_day(api_client) -> dict:
    response = await api_client.get("/air-quality/daily", params=DAY_PARAMS)
    assert response.status_code == 200
    return response.json()["Data"][0]["Days"][0]


def test_codes_in_any_order_build_the_same_key() -> None:
    first = daily_cache_key(["hanoi", "hcmc"], date(2026, 9, 18), date(2026, 9, 19))
    second = daily_cache_key(["hcmc", "hanoi"], date(2026, 9, 18), date(2026, 9, 19))

    assert first == second == "airq:daily:hanoi,hcmc:2026-09-18:2026-09-19"


@pytest.mark.anyio
async def test_reordered_and_recased_locations_share_one_cache_entry(
    api_client, redis_client
) -> None:
    for locations in ("hanoi,hcmc", "HCMC,Hanoi"):
        response = await api_client.get(
            "/air-quality/daily",
            params={"Locations": locations, "From": "2026-09-18", "To": "2026-09-18"},
        )
        assert response.status_code == 200

    assert await _daily_keys(redis_client) == ["airq:daily:hanoi,hcmc:2026-09-18:2026-09-18"]


@pytest.mark.anyio
async def test_second_request_is_served_from_cache(
    make_open_meteo_client, settings, redis_client, api_client, test_engine
) -> None:
    now = _now()
    await take_snapshot(
        make_open_meteo_client(
            run_at=now - timedelta(hours=2), available_at=now - timedelta(hours=1)
        ),
        settings,
        redis_client,
    )
    first = await api_client.get("/air-quality/daily", params=DAY_PARAMS)

    # Emptying the table behind the cache: only a cache hit can still return the old day.
    async with test_engine.begin() as connection:
        await connection.execute(delete(AirReadingRow))
    second = await api_client.get("/air-quality/daily", params=DAY_PARAMS)

    assert first.json()["Data"] == second.json()["Data"]
    assert first.json()["Data"][0]["Days"][0]["AvgPm2_5"] == 12.5
    ttl = await redis_client.ttl("airq:daily:hanoi:2026-09-18:2026-09-18")
    assert 0 < ttl <= settings.daily_cache_ttl_seconds


@pytest.mark.anyio
async def test_new_snapshot_invalidates_cached_daily(
    make_open_meteo_client, settings, redis_client, api_client
) -> None:
    now = _now()
    older = make_open_meteo_client(
        run_at=now - timedelta(hours=14), available_at=now - timedelta(hours=13)
    )
    newer = make_open_meteo_client(
        run_at=now - timedelta(hours=2),
        available_at=now - timedelta(hours=1),
        pm2_5_offset=10.0,
    )

    await take_snapshot(older, settings, redis_client)
    before = await _hanoi_day(api_client)
    await take_snapshot(newer, settings, redis_client)
    after = await _hanoi_day(api_client)

    assert before["AvgPm2_5"] == 12.5
    assert after["AvgPm2_5"] == 22.5


@pytest.mark.anyio
async def test_daily_falls_back_to_the_database_when_redis_is_down(
    make_open_meteo_client, settings, redis_client, api_client
) -> None:
    now = _now()
    await take_snapshot(
        make_open_meteo_client(
            run_at=now - timedelta(hours=2), available_at=now - timedelta(hours=1)
        ),
        settings,
        redis_client,
    )

    async def unreachable_redis():
        # Nothing listens on this port, so every command raises a connection error.
        redis = Redis.from_url(
            "redis://127.0.0.1:6399/1", socket_connect_timeout=0.2, socket_timeout=0.2
        )
        try:
            yield redis
        finally:
            await redis.aclose()

    app.dependency_overrides[get_redis] = unreachable_redis
    day = await _hanoi_day(api_client)

    assert day["HoursCount"] == 24
    assert day["AvgPm2_5"] == 12.5


@pytest.mark.anyio
@pytest.mark.parametrize(
    "corrupt_value",
    ["not json", '{"code": "hanoi"}', '[{"code": "hanoi"}]'],
    ids=["not-json", "object-not-list", "missing-fields"],
)
async def test_corrupt_cache_entry_is_treated_as_a_miss_and_replaced(
    make_open_meteo_client, settings, redis_client, api_client, corrupt_value: str
) -> None:
    now = _now()
    await take_snapshot(
        make_open_meteo_client(
            run_at=now - timedelta(hours=2), available_at=now - timedelta(hours=1)
        ),
        settings,
        redis_client,
    )
    key = daily_cache_key(["hanoi"], date(2026, 9, 18), date(2026, 9, 18))
    await redis_client.set(key, corrupt_value)

    day = await _hanoi_day(api_client)

    assert day["AvgPm2_5"] == 12.5
    replaced = json.loads(await redis_client.get(key))
    assert replaced[0]["code"] == "hanoi"
