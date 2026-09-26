import pytest

HANOI = {
    "Code": "hanoi",
    "Name": "Hà Nội",
    "Latitude": 21.0245,
    "Longitude": 105.84117,
    "Timezone": "Asia/Ho_Chi_Minh",
}


@pytest.mark.anyio
@pytest.mark.parametrize("code", ["hanoi", "HANOI", "HaNoi"])
async def test_location_is_found_by_code_in_any_case(api_client, code: str) -> None:
    response = await api_client.get(f"/locations/{code}")

    assert response.status_code == 200
    assert response.json()["Data"] == HANOI


@pytest.mark.anyio
async def test_unknown_location_code_returns_404_envelope(api_client) -> None:
    response = await api_client.get("/locations/atlantis")

    assert response.status_code == 404
    body = response.json()
    assert body["Data"] is None
    assert body["Error"]["Code"] == "NOT_FOUND"
    assert "atlantis" in body["Error"]["Message"]
