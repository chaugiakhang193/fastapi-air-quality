from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx2

from app.schemas.location import Location

HOURLY_METRICS = "pm2_5,pm10,us_aqi,european_aqi"
# CAMS global snaps requested coordinates to a ~0.4-degree model grid cell, so
# a matching result can be off by close to that much; the tolerance below is
# wide enough to absorb that snap while still catching a genuine order
# mismatch, since the seeded locations are all several degrees apart.
_ORDER_CHECK_TOLERANCE_DEGREES = 1.0


@dataclass
class ModelRunMeta:
    run_at: datetime
    available_at: datetime


async def fetch_meta(client: httpx2.AsyncClient, url: str) -> ModelRunMeta:
    response = await client.get(url)
    response.raise_for_status()
    payload = response.json()
    # The live metadata fields are Unix epoch seconds, so UTC conversion keeps the
    # stored instant independent of the local timezone used by the hourly request.
    return ModelRunMeta(
        run_at=datetime.fromtimestamp(payload["last_run_initialisation_time"], tz=UTC),
        available_at=datetime.fromtimestamp(payload["last_run_availability_time"], tz=UTC),
    )


async def fetch_hourly(
    client: httpx2.AsyncClient,
    url: str,
    locations: Sequence[Location],
    past_days: int = 0,
) -> list[dict]:
    if not locations:
        return []
    # One request per distinct timezone: a single Open-Meteo call only takes
    # one `timezone` value for every coordinate in it, so locations in
    # different zones cannot share a request without mislabelling their
    # local hours. All five seeded locations share Asia/Ho_Chi_Minh today,
    # so this still issues exactly one request in practice.
    results_by_code: dict[str, dict] = {}
    for tz, group in _group_by_timezone(locations):
        results_by_code.update(
            await _fetch_hourly_single_timezone(client, url, group, tz, past_days)
        )
    return [results_by_code[location.code] for location in locations]


def _group_by_timezone(locations: Sequence[Location]) -> list[tuple[str, list[Location]]]:
    groups: dict[str, list[Location]] = {}
    for location in locations:
        groups.setdefault(location.timezone, []).append(location)
    return list(groups.items())


async def _fetch_hourly_single_timezone(
    client: httpx2.AsyncClient,
    url: str,
    locations: Sequence[Location],
    tz: str,
    past_days: int,
) -> dict[str, dict]:
    # One request for every location in this group: Open-Meteo accepts
    # comma-separated latitude/longitude and returns one array entry per
    # coordinate. Open-Meteo does not publish an explicit ordering contract
    # for multi-coordinate requests, so _validate_response_order() below
    # checks each result's own latitude/longitude against the location it is
    # about to be paired with instead of trusting positional order blindly.
    params = {
        "latitude": ",".join(str(location.latitude) for location in locations),
        "longitude": ",".join(str(location.longitude) for location in locations),
        "hourly": HOURLY_METRICS,
        "forecast_days": 1,
        "past_days": past_days,
        "domains": "cams_global",
        "timezone": tz,
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
    _validate_response_order(locations, payload)
    return {location.code: result for location, result in zip(locations, payload, strict=True)}


def _validate_response_order(locations: Sequence[Location], payload: list[dict]) -> None:
    for location, result in zip(locations, payload, strict=True):
        response_latitude = result["latitude"]
        response_longitude = result["longitude"]
        latitude_offset = abs(response_latitude - location.latitude)
        longitude_offset = abs(response_longitude - location.longitude)
        # Response coordinates are snapped to the CAMS model grid, so they
        # rarely equal the requested coordinate exactly. A distance-based
        # tolerance is used instead of equality so a correctly ordered
        # result is never flagged as a mismatch.
        if (
            latitude_offset > _ORDER_CHECK_TOLERANCE_DEGREES
            or longitude_offset > _ORDER_CHECK_TOLERANCE_DEGREES
        ):
            raise ValueError(
                f"Open-Meteo result order mismatch: expected {location.code} near "
                f"({location.latitude}, {location.longitude}), got "
                f"({response_latitude}, {response_longitude})"
            )
