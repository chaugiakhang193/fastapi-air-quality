import asyncio

import httpx2
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.db import get_session
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


@pytest.fixture(autouse=True)
def settings_override():
    settings = get_settings()
    settings.snapshot_min_available_delay_minutes = 0
    app.dependency_overrides[get_settings] = lambda: settings
    yield settings
    app.dependency_overrides.pop(get_settings, None)


@pytest.fixture
def settings():
    settings = get_settings()
    settings.snapshot_min_available_delay_minutes = 0
    return settings


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


def _hourly_payload(latitude: float, longitude: float) -> dict:
    times = [f"2026-09-18T{hour:02d}:00" for hour in range(24)]
    return {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": {
            "time": times,
            "pm2_5": [float(hour + 1) for hour in range(24)],
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
