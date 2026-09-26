from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.envelope import EnvelopeRoute
from app.core.timing import log_duration
from app.repositories.locations import get_location_by_code, list_locations
from app.schemas.location import Location

router = APIRouter(prefix="/locations", tags=["locations"], route_class=EnvelopeRoute)


@router.get("")
@log_duration
async def get_locations(session: AsyncSession = Depends(get_session)) -> list[Location]:
    rows = await list_locations(session)
    return [Location.model_validate(row) for row in rows]


@router.get("/{code}")
async def get_location(code: str, session: AsyncSession = Depends(get_session)) -> Location:
    # Stored codes are lowercase; normalising here matches how the Locations
    # query parameter treats "HANOI" and "hanoi" as the same code.
    row = await get_location_by_code(session, code.strip().lower())
    if row is None:
        raise HTTPException(status_code=404, detail=f"Unknown location code: {code}")
    return Location.model_validate(row)
