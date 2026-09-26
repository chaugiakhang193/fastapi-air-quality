import asyncio
import logging

import httpx2
from redis.asyncio import Redis

from app.core.settings import Settings
from app.services.snapshot_service import SnapshotLockHeldError, take_snapshot

logger = logging.getLogger("airq.scheduler")


async def run_snapshot_scheduler(
    client: httpx2.AsyncClient, settings: Settings, redis: Redis, interval_seconds: float
) -> None:
    # Runs until the lifespan cancels it. The first pass starts immediately, so
    # a machine that was off catches up at once: past_days covers the gap.
    while True:
        try:
            result = await take_snapshot(client, settings, redis)
            logger.info("scheduled snapshot status=%s run_at=%s", result.status, result.run_at)
        except SnapshotLockHeldError:
            logger.info("scheduled snapshot skipped: another run holds the lock")
        except Exception:
            # take_snapshot has already recorded the failure in snapshot_run;
            # the loop has to outlive it or the schedule stops silently.
            logger.exception("scheduled snapshot failed")
        await asyncio.sleep(interval_seconds)
