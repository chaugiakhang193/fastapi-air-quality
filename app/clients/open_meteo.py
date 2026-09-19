from collections.abc import Sequence

import httpx2

from app.schemas.location import Location

HOURLY_METRICS = "pm2_5,pm10,us_aqi,european_aqi"


async def fetch_hourly(
    client: httpx2.AsyncClient,
    url: str,
    locations: Sequence[Location],
) -> list[dict]:
    # One request for every location: Open-Meteo accepts comma-separated
    # latitude/longitude and returns one array entry per coordinate, in the
    # same order (verified in labs/00_probe_open_meteo.py).
    params = {
        "latitude": ",".join(str(location.latitude) for location in locations),
        "longitude": ",".join(str(location.longitude) for location in locations),
        "hourly": HOURLY_METRICS,
        "forecast_days": 1,
        "domains": "cams_global",
        "timezone": "Asia/Ho_Chi_Minh",
    }
    response = await client.get(url, params=params)
    response.raise_for_status()
    payload = response.json()
    if isinstance(payload, dict):
        # Open-Meteo drops the array wrapper and returns a bare object when
        # only one coordinate is requested; multi-location calls always come
        # back as a list, one entry per coordinate, in request order
        # (verified against the live API with one- and two-location calls).
        payload = [payload]
    if not isinstance(payload, list) or len(payload) != len(locations):
        raise ValueError("Expected one Open-Meteo result per requested location")
    return payload
