"""Which ways of calling an ASGI app from a test actually run its lifespan?

Three callers are compared against one minimal app whose lifespan sets a
flag on app.state. Each case prints whether startup ran and what a handler
that reads app.state saw.

Run: uv run python labs/05_lifespan_in_test_clients.py
"""

import asyncio
from contextlib import asynccontextmanager

import httpx2
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

events: list[str] = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    events.append("startup")
    app.state.resource = "created in lifespan"
    yield
    events.append("shutdown")
    del app.state.resource


app = FastAPI(lifespan=lifespan)


@app.get("/resource")
async def read_resource(request: Request) -> dict:
    return {"resource": getattr(request.app.state, "resource", None)}


def report(case: str, status_code: int, body: str) -> None:
    print(f"{case}")
    print(f"  lifespan events: {events}")
    print(f"  response: {status_code} {body}")
    print()
    events.clear()


def case_test_client_without_with() -> None:
    client = TestClient(app)
    response = client.get("/resource")
    report("1. TestClient(app) without `with`", response.status_code, response.text)


def case_test_client_with_with() -> None:
    with TestClient(app) as client:
        response = client.get("/resource")
    report("2. `with TestClient(app)`", response.status_code, response.text)


async def case_asgi_transport() -> None:
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/resource")
    report("3. AsyncClient + ASGITransport", response.status_code, response.text)


if __name__ == "__main__":
    case_test_client_without_with()
    case_test_client_with_with()
    asyncio.run(case_asgi_transport())
