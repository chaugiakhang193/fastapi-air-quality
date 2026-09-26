from datetime import datetime

from sqlalchemy import Row, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ModelRunRow, SnapshotRunRow


async def list_snapshot_runs(
    session: AsyncSession, limit: int, before_id: int | None
) -> list[Row[tuple[SnapshotRunRow, datetime | None]]]:
    # Keyset pagination on the primary key: new runs only ever get higher ids,
    # so a page boundary stays put while the cron keeps inserting rows.
    statement = (
        select(SnapshotRunRow, ModelRunRow.run_at)
        .outerjoin(ModelRunRow, ModelRunRow.id == SnapshotRunRow.model_run_id)
        .order_by(SnapshotRunRow.id.desc())
        .limit(limit)
    )
    if before_id is not None:
        statement = statement.where(SnapshotRunRow.id < before_id)
    return list((await session.execute(statement)).all())
