from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import LocationRow


async def list_locations(session: AsyncSession) -> list[LocationRow]:
    return list((await session.scalars(select(LocationRow).order_by(LocationRow.id))).all())


async def get_location_by_code(session: AsyncSession, code: str) -> LocationRow | None:
    return await session.scalar(select(LocationRow).where(LocationRow.code == code))
