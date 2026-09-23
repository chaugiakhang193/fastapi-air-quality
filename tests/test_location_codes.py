import httpx2
import pytest

from app.api.air_quality import get_http_client
from app.main import app
from app.schemas.air_quality import split_locations

DAILY_RANGE = {"From": "2026-09-18", "To": "2026-09-18"}


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("hanoi", ["hanoi"]),
        (" hanoi , hcmc ", ["hanoi", "hcmc"]),
        ("HANOI,Hcmc", ["hanoi", "hcmc"]),
        ("hanoi,hcmc,HANOI", ["hanoi", "hcmc"]),
        ("hcmc,hanoi", ["hcmc", "hanoi"]),
        ("hanoi,,hcmc,", ["hanoi", "hcmc"]),
    ],
    ids=["single", "whitespace", "mixed-case", "duplicate", "order-kept", "extra-commas"],
)
def test_split_locations_normalises_codes(raw: str, expected: list[str]) -> None:
    assert split_locations(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["", "   ", ",", ",,,", " , , "],
    ids=["empty", "spaces", "one-comma", "commas", "commas-and-spaces"],
)
def test_split_locations_rejects_blank_input(raw: str) -> None:
    with pytest.raises(ValueError, match="at least one code"):
        split_locations(raw)


@pytest.fixture
def use_http_client():
    def install(client_factory) -> None:
        app.dependency_overrides[get_http_client] = client_factory

    yield install
    app.dependency_overrides.pop(get_http_client, None)


def _upstream_must_not_be_called() -> httpx2.AsyncClient:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise AssertionError("Open-Meteo must not be called for invalid Locations")

    return httpx2.AsyncClient(transport=httpx2.MockTransport(handler))


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("path", "extra_params"),
    [("/air-quality/hourly", {}), ("/air-quality/daily", DAILY_RANGE)],
    ids=["hourly", "daily"],
)
async def test_blank_locations_is_rejected_on_both_endpoints(
    api_client, use_http_client, path: str, extra_params: dict
) -> None:
    use_http_client(_upstream_must_not_be_called)
    response = await api_client.get(path, params={"Locations": " , ", **extra_params})

    assert response.status_code == 422
    body = response.json()
    assert body["Data"] is None
    assert body["Error"]["Code"] == "VALIDATION_ERROR"


@pytest.mark.anyio
async def test_hourly_requests_each_location_once_regardless_of_case(
    api_client, use_http_client
) -> None:
    requested_latitudes: list[str] = []

    def recording_client() -> httpx2.AsyncClient:
        def handler(request: httpx2.Request) -> httpx2.Response:
            requested_latitudes.append(request.url.params["latitude"])
            hourly = {
                "time": ["2026-09-19T00:00"],
                "pm2_5": [10.0],
                "pm10": [15.0],
                "us_aqi": [42],
                "european_aqi": [30],
            }
            return httpx2.Response(
                200, json={"latitude": 21.0245, "longitude": 105.84117, "hourly": hourly}
            )

        return httpx2.AsyncClient(transport=httpx2.MockTransport(handler))

    use_http_client(recording_client)
    response = await api_client.get(
        "/air-quality/hourly", params={"Locations": "HANOI, hanoi ,Hanoi"}
    )

    assert response.status_code == 200
    assert [entry["Code"] for entry in response.json()["Data"]] == ["hanoi"]
    assert requested_latitudes == ["21.0245"]
