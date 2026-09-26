import asyncio
from datetime import datetime

import httpx2
import pytest
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.db import get_session
from app.core.redis import get_redis
from app.core.settings import get_settings
from app.main import app
from app.models import Base, LocationRow

SEED_LOCATIONS = [
    {
        "code": "hanoi",
        "name": "Hà Nội",
        "latitude": 21.0245,
        "longitude": 105.84117,
        "timezone": "Asia/Ho_Chi_Minh",
    },
    {
        "code": "hcmc",
        "name": "Thành phố Hồ Chí Minh",
        "latitude": 10.82302,
        "longitude": 106.62965,
        "timezone": "Asia/Ho_Chi_Minh",
    },
    {
        "code": "danang",
        "name": "Đà Nẵng",
        "latitude": 16.06778,
        "longitude": 108.22083,
        "timezone": "Asia/Ho_Chi_Minh",
    },
    {
        "code": "dienbienphu",
        "name": "Điện Biên Phủ",
        "latitude": 21.38602,
        "longitude": 103.02301,
        "timezone": "Asia/Ho_Chi_Minh",
    },
    {
        "code": "dalat",
        "name": "Đà Lạt",
        "latitude": 11.94646,
        "longitude": 108.44193,
        "timezone": "Asia/Ho_Chi_Minh",
    },
]


@pytest.fixture(scope="session")
def test_engine():
    url = get_settings().database_url.replace("/air_quality", "/air_quality_test")
    engine = create_async_engine(url, pool_pre_ping=True, poolclass=NullPool)

    async def setup() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            if await session.scalar(text("SELECT COUNT(*) FROM location")) == 0:
                session.add_all([LocationRow(**values) for values in SEED_LOCATIONS])
                await session.commit()

    asyncio.run(setup())
    yield engine
    asyncio.run(engine.dispose())


@pytest.fixture(autouse=True)
def override_database(test_engine, monkeypatch):
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)

    async def test_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = test_session

    import app.core.db as db_module
    import app.services.snapshot_service as snapshot_module

    monkeypatch.setattr(db_module, "async_session_factory", session_factory)
    monkeypatch.setattr(snapshot_module, "async_session_factory", session_factory)
    yield
    app.dependency_overrides.pop(get_session, None)


@pytest.fixture
def settings():
    # model_copy() leaves the lru_cache'd instance from get_settings()
    # untouched, so a test that changes a field cannot leak it into later tests.
    return get_settings().model_copy(update={"snapshot_min_available_delay_minutes": 0})


@pytest.fixture(autouse=True)
def settings_override(settings):
    app.dependency_overrides[get_settings] = lambda: settings
    yield settings
    app.dependency_overrides.pop(get_settings, None)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def clean_database(test_engine):
    async def clean() -> None:
        session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
        async with session_factory() as session:
            await session.execute(
                text(
                    "TRUNCATE TABLE snapshot_run, air_reading, "
                    "snapshot, model_run RESTART IDENTITY CASCADE"
                )
            )
            await session.commit()

    asyncio.run(clean())


@pytest.fixture
async def db_session(test_engine):
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest.fixture
async def api_client():
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url="http://test"
    ) as http_client:
        yield http_client


def _hourly_payload(latitude: float, longitude: float, pm2_5_offset: float = 0.0) -> dict:
    times = [f"2026-09-18T{hour:02d}:00" for hour in range(24)]
    return {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": {
            "time": times,
            "pm2_5": [float(hour + 1) + pm2_5_offset for hour in range(24)],
            "pm10": [float(hour + 2) for hour in range(24)],
            "us_aqi": [hour + 10 for hour in range(24)],
            "european_aqi": [hour + 5 for hour in range(24)],
        },
    }


@pytest.fixture
async def client():
    payloads = [_hourly_payload(loc["latitude"], loc["longitude"]) for loc in SEED_LOCATIONS]

    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path.endswith("meta.json"):
            return httpx2.Response(
                200,
                json={
                    "last_run_initialisation_time": 1789718400,
                    "last_run_availability_time": 1789714800,
                },
            )
        return httpx2.Response(200, json=payloads)

    async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as http_client:
        yield http_client


@pytest.fixture
async def slow_client():
    payloads = [_hourly_payload(loc["latitude"], loc["longitude"]) for loc in SEED_LOCATIONS]

    async def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path.endswith("meta.json"):
            await asyncio.sleep(0.3)
            return httpx2.Response(
                200,
                json={
                    "last_run_initialisation_time": 1789718400,
                    "last_run_availability_time": 1789714800,
                },
            )
        return httpx2.Response(200, json=payloads)

    async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as http_client:
        yield http_client


@pytest.fixture
async def make_open_meteo_client():
    created: list[httpx2.AsyncClient] = []

    def factory(
        *,
        run_at: datetime,
        available_at: datetime,
        pm2_5_offset: float = 0.0,
        meta_status: int = 200,
        hourly_status: int = 200,
    ) -> httpx2.AsyncClient:
        def handler(request: httpx2.Request) -> httpx2.Response:
            if request.url.path.endswith("meta.json"):
                if meta_status != 200:
                    return httpx2.Response(meta_status, json={"reason": "meta failed"})
                return httpx2.Response(
                    200,
                    json={
                        "last_run_initialisation_time": int(run_at.timestamp()),
                        "last_run_availability_time": int(available_at.timestamp()),
                    },
                )
            if hourly_status != 200:
                return httpx2.Response(hourly_status, json={"reason": "hourly failed"})
            return httpx2.Response(
                200,
                json=[
                    _hourly_payload(loc["latitude"], loc["longitude"], pm2_5_offset)
                    for loc in SEED_LOCATIONS
                ],
            )

        http_client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
        created.append(http_client)
        return http_client

    yield factory
    for http_client in created:
        await http_client.aclose()


def _test_redis_url() -> str:
    # DB 1 keeps test keys away from the development cache in DB 0.
    return get_settings().redis_url.rsplit("/", 1)[0] + "/1"


@pytest.fixture(autouse=True)
def clean_redis():
    async def clean() -> None:
        redis = Redis.from_url(_test_redis_url(), decode_responses=True)
        try:
            await redis.flushdb()
        finally:
            await redis.aclose()

    asyncio.run(clean())


@pytest.fixture(autouse=True)
def override_redis():
    # A client per request: a client created in a fixture's asyncio.run()
    # loop cannot be reused from the loop that serves the request.
    async def test_redis():
        redis = Redis.from_url(_test_redis_url(), decode_responses=True)
        try:
            yield redis
        finally:
            await redis.aclose()

    app.dependency_overrides[get_redis] = test_redis
    yield
    app.dependency_overrides.pop(get_redis, None)


@pytest.fixture
async def redis_client():
    redis = Redis.from_url(_test_redis_url(), decode_responses=True)
    yield redis
    await redis.aclose()
