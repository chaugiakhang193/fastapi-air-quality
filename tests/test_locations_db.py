from fastapi.testclient import TestClient

from app.main import app


def test_locations_are_loaded_from_database() -> None:
    with TestClient(app) as client:
        response = client.get("/locations")

    assert response.status_code == 200
    assert len(response.json()["Data"]) == 5
