from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import insert, text
from sqlalchemy.exc import IntegrityError

from app.core.http_client import get_http_client
from app.main import app
from app.models import SnapshotRunRow, SnapshotRunStatus


def _now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


async def _insert_runs(test_engine, count: int) -> None:
    started = _now() - timedelta(hours=count)
    async with test_engine.begin() as connection:
        await connection.execute(
            insert(SnapshotRunRow),
            [
                {
                    "started_at": started + timedelta(hours=index),
                    "finished_at": started + timedelta(hours=index, seconds=5),
                    "status": SnapshotRunStatus.NO_NEW_DATA,
                }
                for index in range(count)
            ],
        )


@pytest.fixture
def use_http_client():
    def install(http_client) -> None:
        app.dependency_overrides[get_http_client] = lambda: http_client

    yield install
    app.dependency_overrides.pop(get_http_client, None)


@pytest.mark.anyio
async def test_runs_are_paged_newest_first(api_client, test_engine) -> None:
    await _insert_runs(test_engine, 3)

    first = (await api_client.get("/snapshots", params={"Limit": 2})).json()["Data"]
    second = (
        await api_client.get("/snapshots", params={"Limit": 2, "BeforeId": first["NextBeforeId"]})
    ).json()["Data"]

    assert [item["Id"] for item in first["Items"]] == [3, 2]
    assert first["NextBeforeId"] == 2
    assert [item["Id"] for item in second["Items"]] == [1]
    assert second["NextBeforeId"] is None


@pytest.mark.anyio
async def test_exactly_one_full_page_has_no_next_page(api_client, test_engine) -> None:
    await _insert_runs(test_engine, 2)

    data = (await api_client.get("/snapshots", params={"Limit": 2})).json()["Data"]

    assert len(data["Items"]) == 2
    assert data["NextBeforeId"] is None


@pytest.mark.anyio
@pytest.mark.parametrize(
    "params",
    [{"Limit": 0}, {"Limit": 101}, {"BeforeId": 0}, {"limit": 5}, {"Page": 2}],
    ids=["limit-zero", "limit-too-big", "before-id-zero", "lowercase-name", "unknown-key"],
)
async def test_invalid_page_parameters_return_422(api_client, params: dict) -> None:
    response = await api_client.get("/snapshots", params=params)

    assert response.status_code == 422
    assert response.json()["Error"]["Code"] == "VALIDATION_ERROR"


@pytest.mark.anyio
async def test_posted_runs_show_run_time_and_hide_error_detail(
    api_client, make_open_meteo_client, settings, use_http_client
) -> None:
    now = _now()
    run_at = now - timedelta(hours=2)
    run_times = {"run_at": run_at, "available_at": now - timedelta(hours=1)}
    headers = {"X-Api-Key": settings.snapshot_api_key}

    use_http_client(make_open_meteo_client(**run_times))
    created = await api_client.post("/snapshots", headers=headers)
    unchanged = await api_client.post("/snapshots", headers=headers)
    items = (await api_client.get("/snapshots")).json()["Data"]["Items"]

    assert (created.status_code, unchanged.status_code) == (201, 200)
    assert [item["Status"] for item in items] == ["no_new_data", "succeeded"]
    assert datetime.fromisoformat(items[1]["RunAt"]) == run_at
    assert "ErrorDetail" not in items[0]


@pytest.mark.anyio
async def test_status_check_rejects_member_names(test_engine) -> None:
    with pytest.raises(IntegrityError, match="ck_snapshot_run_status"):
        async with test_engine.begin() as connection:
            await connection.execute(
                text("INSERT INTO snapshot_run (started_at, status) VALUES (now(), 'SUCCEEDED')")
            )


@pytest.mark.anyio
async def test_failed_run_exposes_error_code_only(
    api_client, make_open_meteo_client, settings, use_http_client
) -> None:
    now = _now()
    use_http_client(
        make_open_meteo_client(
            run_at=now - timedelta(hours=2),
            available_at=now - timedelta(hours=1),
            hourly_status=500,
        )
    )
    response = await api_client.post("/snapshots", headers={"X-Api-Key": settings.snapshot_api_key})
    item = (await api_client.get("/snapshots")).json()["Data"]["Items"][0]

    assert response.status_code == 502
    assert item["Status"] == "failed"
    assert item["ErrorCode"] == "HTTPStatusError"
    assert item["RunAt"] is None
    assert set(item) == {"Id", "StartedAt", "FinishedAt", "Status", "RunAt", "ErrorCode"}
