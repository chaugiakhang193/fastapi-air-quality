import httpx2
import pytest
from fastapi.testclient import TestClient

from app.api.air_quality import get_http_client
from app.clients.open_meteo import fetch_hourly
from app.main import app
from app.schemas.location import Location


def _mock_client() -> httpx2.AsyncClient:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200,
            json=[
                {
                    "latitude": 21.0245,
                    "longitude": 105.84117,
                    "hourly": {"time": ["2026-09-19T00:00"], "pm2_5": [10.0]},
                },
                {
                    "latitude": 10.82302,
                    "longitude": 106.62965,
                    "hourly": {"time": ["2026-09-19T00:00"], "pm2_5": [20.0]},
                },
            ],
        )

    return httpx2.AsyncClient(transport=httpx2.MockTransport(handler))


def test_get_hourly_uses_shared_client_and_open_meteo_shape() -> None:
    app.dependency_overrides[get_http_client] = _mock_client
    try:
        with TestClient(app) as client:
            response = client.get("/air-quality/hourly", params={"Locations": "hanoi,hcmc"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()["Data"]
    assert [entry["Code"] for entry in data] == ["hanoi", "hcmc"]
    assert data[0]["Hourly"]["pm2_5"] == [10.0]
    assert data[1]["Hourly"]["pm2_5"] == [20.0]


def test_get_hourly_rejects_unknown_location_code() -> None:
    with TestClient(app) as client:
        response = client.get("/air-quality/hourly", params={"Locations": "atlantis"})

    assert response.status_code == 404
    body = response.json()
    assert body["Data"] is None
    assert body["Error"]["Code"] == "NOT_FOUND"


def test_get_hourly_rejects_blank_locations_instead_of_calling_upstream() -> None:
    # ",,," strips down to an empty list; must be rejected before it ever
    # reaches Open-Meteo with blank latitude/longitude.
    with TestClient(app) as client:
        response = client.get("/air-quality/hourly", params={"Locations": ",,,"})

    assert response.status_code == 422
    body = response.json()
    assert body["Data"] is None
    assert body["Error"]["Code"] == "VALIDATION_ERROR"


def _mock_single_location_client() -> httpx2.AsyncClient:
    def handler(request: httpx2.Request) -> httpx2.Response:
        # A single-coordinate request returns a bare JSON object, not a
        # one-item list — checked against the real API.
        hourly = {"time": ["2026-09-19T00:00"], "pm2_5": [10.0]}
        return httpx2.Response(
            200, json={"latitude": 21.0245, "longitude": 105.84117, "hourly": hourly}
        )

    return httpx2.AsyncClient(transport=httpx2.MockTransport(handler))


def test_get_hourly_with_a_single_location_normalises_bare_object_to_list() -> None:
    app.dependency_overrides[get_http_client] = _mock_single_location_client
    try:
        with TestClient(app) as client:
            response = client.get("/air-quality/hourly", params={"Locations": "hanoi"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()["Data"]
    assert [entry["Code"] for entry in data] == ["hanoi"]
    assert data[0]["Hourly"]["pm2_5"] == [10.0]


@pytest.mark.anyio
async def test_fetch_hourly_rejects_a_response_whose_order_does_not_match_the_request() -> None:
    hanoi = Location(
        code="hanoi",
        name="Ha Noi",
        latitude=21.0245,
        longitude=105.84117,
        timezone="Asia/Ho_Chi_Minh",
    )
    hcmc = Location(
        code="hcmc",
        name="Ho Chi Minh City",
        latitude=10.82302,
        longitude=106.62965,
        timezone="Asia/Ho_Chi_Minh",
    )

    def handler(request: httpx2.Request) -> httpx2.Response:
        # hanoi was requested first but this result carries hcmc's coordinates,
        # simulating Open-Meteo returning entries out of request order.
        return httpx2.Response(
            200,
            json=[
                {"latitude": hcmc.latitude, "longitude": hcmc.longitude, "hourly": {}},
                {"latitude": hanoi.latitude, "longitude": hanoi.longitude, "hourly": {}},
            ],
        )

    async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as client:
        with pytest.raises(ValueError, match="order mismatch"):
            await fetch_hourly(client, "https://example.invalid/air-quality", [hanoi, hcmc])


def _mock_upstream_5xx_client() -> httpx2.AsyncClient:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(503, json={"reason": "Open-Meteo is down"})

    return httpx2.AsyncClient(transport=httpx2.MockTransport(handler))


def test_get_hourly_maps_open_meteo_error_response_to_502() -> None:
    app.dependency_overrides[get_http_client] = _mock_upstream_5xx_client
    try:
        with TestClient(app) as client:
            response = client.get("/air-quality/hourly", params={"Locations": "hanoi"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 502
    body = response.json()
    assert body["Data"] is None
    assert body["Error"]["Code"] == "UPSTREAM_ERROR"


def _mock_upstream_timeout_client() -> httpx2.AsyncClient:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectTimeout("timed out")

    return httpx2.AsyncClient(transport=httpx2.MockTransport(handler))


def test_get_hourly_maps_open_meteo_timeout_to_503() -> None:
    app.dependency_overrides[get_http_client] = _mock_upstream_timeout_client
    try:
        with TestClient(app) as client:
            response = client.get("/air-quality/hourly", params={"Locations": "hanoi"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    body = response.json()
    assert body["Data"] is None
    assert body["Error"]["Code"] == "UPSTREAM_UNAVAILABLE"
