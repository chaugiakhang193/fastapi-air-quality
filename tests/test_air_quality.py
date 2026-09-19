import httpx2
from fastapi.testclient import TestClient

from app.api.air_quality import get_http_client
from app.main import app


def _mock_client() -> httpx2.AsyncClient:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200,
            json=[
                {"hourly": {"time": ["2026-09-19T00:00"], "pm2_5": [10.0]}},
                {"hourly": {"time": ["2026-09-19T00:00"], "pm2_5": [20.0]}},
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
    body = response.json()
    assert [entry["Code"] for entry in body] == ["hanoi", "hcmc"]
    assert body[0]["Hourly"]["pm2_5"] == [10.0]
    assert body[1]["Hourly"]["pm2_5"] == [20.0]


def test_get_hourly_rejects_unknown_location_code() -> None:
    with TestClient(app) as client:
        response = client.get("/air-quality/hourly", params={"Locations": "atlantis"})

    assert response.status_code == 404


def test_get_hourly_rejects_blank_locations_instead_of_calling_upstream() -> None:
    # ",,," strips down to an empty list; must be rejected before it ever
    # reaches Open-Meteo with blank latitude/longitude.
    with TestClient(app) as client:
        response = client.get("/air-quality/hourly", params={"Locations": ",,,"})

    assert response.status_code == 422


def _mock_single_location_client() -> httpx2.AsyncClient:
    def handler(request: httpx2.Request) -> httpx2.Response:
        # A single-coordinate request returns a bare JSON object, not a
        # one-item list — checked against the real API.
        hourly = {"time": ["2026-09-19T00:00"], "pm2_5": [10.0]}
        return httpx2.Response(200, json={"hourly": hourly})

    return httpx2.AsyncClient(transport=httpx2.MockTransport(handler))


def test_get_hourly_with_a_single_location_normalises_bare_object_to_list() -> None:
    app.dependency_overrides[get_http_client] = _mock_single_location_client
    try:
        with TestClient(app) as client:
            response = client.get("/air-quality/hourly", params={"Locations": "hanoi"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert [entry["Code"] for entry in body] == ["hanoi"]
    assert body[0]["Hourly"]["pm2_5"] == [10.0]
