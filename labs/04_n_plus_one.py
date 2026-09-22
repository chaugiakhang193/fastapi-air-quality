"""Count the extra queries produced by an N+1 style loop."""

import asyncio

from sqlalchemy import event, select

from app.core.db import async_session_factory, engine
from app.models import LocationRow

query_count = 0


def _count_queries(*_args: object) -> None:
    global query_count
    query_count += 1


async def main() -> None:
    global query_count
    event.listen(engine.sync_engine, "before_cursor_execute", _count_queries)

    query_count = 0
    async with async_session_factory() as session:
        locations = (await session.scalars(select(LocationRow))).all()
        for location in locations:
            await session.scalar(select(LocationRow).where(LocationRow.id == location.id))
    print(f"N+1 style: {query_count} queries for {len(locations)} locations")

    query_count = 0
    async with async_session_factory() as session:
        await session.scalars(select(LocationRow))
    print(f"single select: {query_count} query")


if __name__ == "__main__":
    asyncio.run(main())
