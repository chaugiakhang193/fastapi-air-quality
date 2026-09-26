from fastapi import Request
from redis.asyncio import Redis

from app.core.settings import Settings


def create_redis(settings: Settings) -> Redis:
    # Short socket timeouts keep a stopped Redis from stalling requests: the
    # daily cache treats Redis errors as a miss and falls back to the database.
    return Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=settings.redis_timeout_seconds,
        socket_timeout=settings.redis_timeout_seconds,
    )


def get_redis(request: Request) -> Redis:
    # Created once in main.py's lifespan, like the shared HTTP client.
    return request.app.state.redis
