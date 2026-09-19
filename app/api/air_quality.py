import httpx2
from fastapi import APIRouter, Depends, HTTPException, Request

from app.clients.open_meteo import fetch_hourly
from app.core.settings import Settings, get_settings
from app.data.locations import get_location
from app.schemas.location import Location

router = APIRouter(prefix="/air-quality", tags=["air-quality"])


def get_http_client(request: Request) -> httpx2.AsyncClient:
    # Created once in main.py's lifespan and stored on app.state so every
    # request reuses the same connection pool instead of opening a new one.
    return request.app.state.http_client


def parse_locations(locations: str) -> list[Location]:
    codes = [code.strip() for code in locations.split(",") if code.strip()]
    if not codes:
        # "" or ",,," both split down to an empty list; without this check,
        # Open-Meteo would be called with blank latitude/longitude instead
        # of the request being rejected up front.
        raise HTTPException(status_code=422, detail="Locations must contain at least one code")
    resolved: list[Location] = []
    for code in codes:
        location = get_location(code)
        if location is None:
            raise HTTPException(status_code=404, detail=f"Unknown location code: {code}")
        resolved.append(location)
    return resolved


@router.get("/hourly")
async def get_hourly(
    Locations: str,
    client: httpx2.AsyncClient = Depends(get_http_client),
    settings: Settings = Depends(get_settings),
) -> list[dict]:
    # No database yet: this calls Open-Meteo directly on every request and
    # returns its shape almost as-is. A stable contract (envelope, caching,
    # persistence) is future work once storage exists.
    locations = parse_locations(Locations)
    results = await fetch_hourly(client, settings.open_meteo_air_quality_url, locations)
    return [
        {"Code": location.code, "Name": location.name, "Hourly": result["hourly"]}
        for location, result in zip(locations, results, strict=True)
    ]
