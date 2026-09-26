import httpx2
from fastapi import Request


def get_http_client(request: Request) -> httpx2.AsyncClient:
    # Created once in main.py's lifespan so every request reuses one connection pool.
    return request.app.state.http_client
