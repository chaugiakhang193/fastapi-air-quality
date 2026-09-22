from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.timing import log_duration
from app.repositories.locations import list_locations
from app.schemas.location import Location

router = APIRouter(prefix="/locations", tags=["locations"])


@router.get("")
@log_duration
async def get_locations(session: AsyncSession = Depends(get_session)) -> list[Location]:
    rows = await list_locations(session)
    return [
        Location(
            code=row.code,
            name=row.name,
            latitude=row.latitude,
            longitude=row.longitude,
            timezone=row.timezone,
        )
        for row in rows
    ]
