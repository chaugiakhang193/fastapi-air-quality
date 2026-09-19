from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

call_count = 0


def counted_dependency() -> int:
    global call_count
    call_count += 1
    return call_count


def needs_it_directly(value: int = Depends(counted_dependency)) -> int:
    return value


def needs_it_indirectly(value: int = Depends(counted_dependency)) -> int:
    return value


probe_app = FastAPI()


@probe_app.get("/diamond")
def diamond(
    direct: int = Depends(needs_it_directly),
    indirect: int = Depends(needs_it_indirectly),
) -> dict[str, int]:
    return {"direct": direct, "indirect": indirect}


def test_dependency_used_twice_in_one_request_runs_once() -> None:
    global call_count
    call_count = 0
    client = TestClient(probe_app)

    first = client.get("/diamond")
    second = client.get("/diamond")

    # Both branches of the diamond see the same value within one request —
    # FastAPI caches a dependency's result per request by default
    # (use_cache=True) — but a second, separate request re-runs it.
    assert first.json() == {"direct": 1, "indirect": 1}
    assert second.json() == {"direct": 2, "indirect": 2}
