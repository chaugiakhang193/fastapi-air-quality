"""Where does a type imported only under TYPE_CHECKING break?

The same annotation is used by a plain function, a Pydantic model, and a
FastAPI route. Each case runs on its own and prints either its result or the
exception it raised, so the output shows at which step the failure appears.

Annotations are quoted on purpose, so the outcome does not depend on how
Python 3.14 defers annotation evaluation (PEP 649).

Run: uv run python labs/06_type_checking_in_pydantic.py
"""

import sys
from collections.abc import Callable
from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

if TYPE_CHECKING:
    from decimal import Decimal


def describe(amount: "Decimal") -> str:  # noqa: UP037
    return f"describe() received {amount!r}"


def run_case(label: str, action: Callable[[], str]) -> None:
    try:
        print(f"[{label}] ok -> {action()}")
    except Exception as exc:  # noqa: BLE001 - the lab reports whatever is raised
        print(f"[{label}] {type(exc).__name__}: {exc}")


def _price_app() -> FastAPI:
    class Price(BaseModel):
        amount: "Decimal"  # noqa: UP037

    lab_app = FastAPI()

    @lab_app.get("/price")
    async def read_price() -> Price:
        return Price(amount="1.50")

    return lab_app


def case_plain_function() -> str:
    return describe(1)


def case_define_model() -> str:
    class Price(BaseModel):
        amount: "Decimal"  # noqa: UP037

    return f"class created, __pydantic_complete__={Price.__pydantic_complete__}"


def case_instantiate_model() -> str:
    class Price(BaseModel):
        amount: "Decimal"  # noqa: UP037

    return repr(Price(amount="1.50"))


def case_fastapi_route() -> str:
    lab_app = _price_app()
    return f"route registered at {lab_app.routes[-1].path}"


def case_fastapi_request() -> str:
    with TestClient(_price_app()) as client:
        response = client.get("/price")
    return f"GET /price -> {response.status_code} {response.text}"


def case_runtime_import() -> str:
    from decimal import Decimal  # noqa: F401 - used by the annotation below

    class Price(BaseModel):
        amount: Decimal

    return repr(Price(amount="1.50"))


if __name__ == "__main__":
    print(f"Python {sys.version.split()[0]}, TYPE_CHECKING at runtime = {TYPE_CHECKING}")
    run_case("plain function", case_plain_function)
    run_case("define model", case_define_model)
    run_case("instantiate model", case_instantiate_model)
    run_case("FastAPI route", case_fastapi_route)
    run_case("FastAPI request", case_fastapi_request)
    run_case("runtime import", case_runtime_import)
