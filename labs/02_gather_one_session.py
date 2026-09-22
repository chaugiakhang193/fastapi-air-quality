"""Show why concurrent operations need separate async sessions."""

import asyncio

from sqlalchemy import text

from app.core.db import async_session_factory


async def main() -> None:
    async with async_session_factory() as session:
        try:
            await asyncio.gather(
                session.execute(text("SELECT pg_sleep(0.2)")),
                session.execute(text("SELECT pg_sleep(0.2)")),
            )
        except Exception as exc:
            print(f"gather on one AsyncSession failed: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    asyncio.run(main())
