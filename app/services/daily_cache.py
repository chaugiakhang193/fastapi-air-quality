import logging
from datetime import date

from pydantic import TypeAdapter, ValidationError
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.schemas.air_quality import LocationDaily

logger = logging.getLogger("airq.cache")

DAILY_KEY_PREFIX = "airq:daily:"
_daily_adapter = TypeAdapter(list[LocationDaily])


def daily_cache_key(codes: list[str], date_from: date, date_to: date) -> str:
    # Codes arrive lowercased and de-duplicated by split_locations. Sorting
    # them lets "hanoi,hcmc" and "hcmc,hanoi" share one entry, which is safe
    # because the daily query orders its rows by location code.
    joined_codes = ",".join(sorted(codes))
    return f"{DAILY_KEY_PREFIX}{joined_codes}:{date_from.isoformat()}:{date_to.isoformat()}"


async def read_daily(redis: Redis, key: str) -> list[LocationDaily] | None:
    try:
        raw = await redis.get(key)
    except RedisError:
        logger.warning("daily cache read failed, using the database", exc_info=True)
        return None
    if raw is None:
        return None
    try:
        return _daily_adapter.validate_json(raw)
    except ValidationError:
        # An entry that no longer matches LocationDaily (for example, written
        # before a schema change) is a miss; the route's write replaces it.
        logger.warning("daily cache entry is invalid, using the database key=%s", key)
        return None


async def write_daily(redis: Redis, key: str, value: list[LocationDaily], ttl_seconds: int) -> None:
    try:
        await redis.set(key, _daily_adapter.dump_json(value), ex=ttl_seconds)
    except RedisError:
        logger.warning("daily cache write failed", exc_info=True)


async def invalidate_daily(redis: Redis) -> int:
    # SCAN walks the keyspace in batches instead of blocking Redis the way
    # KEYS does. A failure here leaves stale entries that expire by TTL; the
    # snapshot itself has already been committed, so it is not failed.
    deleted = 0
    try:
        async for key in redis.scan_iter(match=f"{DAILY_KEY_PREFIX}*", count=100):
            deleted += await redis.delete(key)
    except RedisError:
        logger.warning("daily cache invalidation failed", exc_info=True)
    return deleted
