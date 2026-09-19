from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

events: list[str] = []


async def tracked_resource():
    events.append("dependency:before-yield")
    yield "value"
    events.append("dependency:after-yield")


probe_app = FastAPI()


@probe_app.middleware("http")
async def timing(request, call_next):
    response = await call_next(request)
    events.append("middleware:after-call-next")
    return response


@probe_app.get("/resource")
async def read_resource(value: str = Depends(tracked_resource)) -> dict[str, str]:
    events.append("endpoint:handler")
    return {"value": value}


def test_yield_cleanup_runs_after_response_leaves_call_next() -> None:
    events.clear()
    client = TestClient(probe_app)

    client.get("/resource")

    # FastAPI 0.141.1 / Starlette 1.6: cleanup after `yield` runs after
    # call_next() has already returned the response.
    assert events == [
        "dependency:before-yield",
        "endpoint:handler",
        "middleware:after-call-next",
        "dependency:after-yield",
    ]
