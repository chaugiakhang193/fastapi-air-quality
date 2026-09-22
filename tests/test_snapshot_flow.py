import pytest
from sqlalchemy import func, select

from app.models import AirReadingRow, ModelRunRow, SnapshotRunRow
from app.services.snapshot_service import take_snapshot


@pytest.mark.anyio
async def test_second_snapshot_is_unchanged_and_does_not_duplicate_rows(
    client, settings, test_engine
):
    first = await take_snapshot(client, settings)
    async with test_engine.connect() as connection:
        first_count = await connection.scalar(select(func.count()).select_from(AirReadingRow))

    second = await take_snapshot(client, settings)
    async with test_engine.connect() as connection:
        second_count = await connection.scalar(select(func.count()).select_from(AirReadingRow))
        run_count = await connection.scalar(select(func.count()).select_from(ModelRunRow))
        log_count = await connection.scalar(select(func.count()).select_from(SnapshotRunRow))

    assert first.status == "created"
    assert second.status == "unchanged"
    assert second.run_at == first.run_at
    assert second_count == first_count
    assert run_count == 1
    assert log_count == 2
