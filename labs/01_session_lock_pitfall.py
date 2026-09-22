"""Show that a session-level advisory lock survives transaction completion."""

import asyncio

from sqlalchemy import text

from app.core.db import async_session_factory

LOCK_KEY = 999_001


async def main() -> None:
    async with async_session_factory() as first:
        await first.execute(text("SELECT pg_advisory_lock(:key)"), {"key": LOCK_KEY})
        await first.commit()

    async with async_session_factory() as second:
        acquired = (
            await second.execute(
                text("SELECT pg_try_advisory_lock(:key)"),
                {"key": LOCK_KEY},
            )
        ).scalar_one()
        print(f"second session acquired lock: {acquired}")


if __name__ == "__main__":
    asyncio.run(main())
