from fastapi import APIRouter

from app.core.timing import log_duration
from app.data.locations import SEED_LOCATIONS
from app.schemas.location import Location

router = APIRouter(prefix="/locations", tags=["locations"])


@router.get("")
@log_duration
async def list_locations() -> list[Location]:
    return SEED_LOCATIONS
