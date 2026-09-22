"""Keep the lazy-loading failure experiment separate from application code."""

import asyncio

from sqlalchemy import select

from app.core.db import async_session_factory
from app.models import SnapshotRow


async def main() -> None:
    async with async_session_factory() as session:
        snapshot = await session.scalar(select(SnapshotRow).limit(1))
    if snapshot is None:
        print("no snapshot row yet")
        return

    print(f"snapshot location id: {snapshot.location_id}")
    print("No relationship is defined; add one to the model before testing a lazy load.")


if __name__ == "__main__":
    asyncio.run(main())
