import asyncio

import pytest

from app.services.snapshot_service import SnapshotLockHeldError, take_snapshot


@pytest.mark.anyio
async def test_concurrent_snapshots_have_one_lock_holder(slow_client, settings):
    results = await asyncio.gather(
        take_snapshot(slow_client, settings),
        take_snapshot(slow_client, settings),
        return_exceptions=True,
    )

    errors = [result for result in results if isinstance(result, SnapshotLockHeldError)]
    successes = [result for result in results if not isinstance(result, Exception)]
    assert len(errors) == 1
    assert len(successes) == 1
