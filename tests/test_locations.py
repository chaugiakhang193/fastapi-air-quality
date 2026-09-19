from fastapi.testclient import TestClient

from app.main import app


def test_list_locations_returns_all_seed_entries() -> None:
    with TestClient(app) as client:
        response = client.get("/locations")

    assert response.status_code == 200
    body = response.json()
    assert {entry["Code"] for entry in body} == {"hanoi", "hcmc", "danang", "dienbienphu", "dalat"}
    assert body[0] == {
        "Code": "hanoi",
        "Name": "Hà Nội",
        "Latitude": 21.0245,
        "Longitude": 105.84117,
        "Timezone": "Asia/Ho_Chi_Minh",
    }
