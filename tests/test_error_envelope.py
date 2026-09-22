from fastapi.testclient import TestClient

from app.main import app


def test_unmatched_route_still_gets_an_envelope() -> None:
    with TestClient(app) as client:
        response = client.get("/this-route-does-not-exist")

    assert response.status_code == 404
    body = response.json()
    assert body["Data"] is None
    assert body["Error"]["Code"] == "NOT_FOUND"


def test_wrong_method_on_a_real_route_still_gets_an_envelope() -> None:
    with TestClient(app) as client:
        response = client.delete("/locations")

    assert response.status_code == 405
    body = response.json()
    assert body["Data"] is None
    assert body["Error"]["Code"] == "METHOD_NOT_ALLOWED"


def test_snapshot_with_wrong_api_key_returns_enveloped_401() -> None:
    # Header(...) makes X-Api-Key required, so omitting it entirely triggers
    # FastAPI's own 422 before require_snapshot_api_key ever runs — sending a
    # wrong value is what actually exercises its 401 branch.
    with TestClient(app) as client:
        response = client.post("/snapshots", headers={"X-Api-Key": "wrong"})

    assert response.status_code == 401
    body = response.json()
    assert body["Data"] is None
    assert body["Error"]["Code"] == "UNAUTHORIZED"


def test_snapshot_without_api_key_header_returns_enveloped_422() -> None:
    with TestClient(app) as client:
        response = client.post("/snapshots")

    assert response.status_code == 422
    body = response.json()
    assert body["Data"] is None
    assert body["Error"]["Code"] == "VALIDATION_ERROR"
