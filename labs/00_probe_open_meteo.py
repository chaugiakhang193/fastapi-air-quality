"""Inspect the CAMS global metadata and hourly data for five locations."""

import hashlib
import json
import sys
from datetime import UTC, datetime, timedelta, timezone
from urllib.request import urlopen
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

META_URL = "https://air-quality-api.open-meteo.com/data/cams_global/static/meta.json"
DATA_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
# Windows can lack IANA time zone data; Vietnam's current civil time is UTC+07:00.
try:
    VIETNAM_TIMEZONE = ZoneInfo("Asia/Ho_Chi_Minh")
except ZoneInfoNotFoundError:
    VIETNAM_TIMEZONE = timezone(timedelta(hours=7), name="Asia/Ho_Chi_Minh")
GRID_STEP = 0.4
LOCATIONS = (
    ("Hà Nội", 21.0245, 105.84117),
    ("TP.HCM", 10.82302, 106.62965),
    ("Đà Nẵng", 16.06778, 108.22083),
    ("Điện Biên Phủ", 21.38602, 103.02301),
    ("Đà Lạt", 11.94646, 108.44193),
)


def fetch_json(url):
    with urlopen(url, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def parse_meta_time(unix_seconds):
    return datetime.fromtimestamp(unix_seconds, UTC).astimezone(VIETNAM_TIMEZONE)


def nearest_grid_coordinate(coordinate, origin):
    return round(origin + round((coordinate - origin) / GRID_STEP) * GRID_STEP, 1)


def main():
    # PowerShell 5.1 can give redirected Python output a legacy encoding.
    sys.stdout.reconfigure(encoding="utf-8")
    metadata = fetch_json(META_URL)
    print(
        "last_run_initialisation_time type: "
        f"{type(metadata['last_run_initialisation_time']).__name__}"
    )
    print(
        f"last_run_availability_time type: {type(metadata['last_run_availability_time']).__name__}"
    )
    initialisation_time = parse_meta_time(metadata["last_run_initialisation_time"])
    availability_time = parse_meta_time(metadata["last_run_availability_time"])
    ready_time = availability_time + timedelta(minutes=10)
    now = datetime.now(VIETNAM_TIMEZONE)

    print(f"Last run initialisation (Asia/Ho_Chi_Minh): {initialisation_time.isoformat()}")
    print(f"Last run availability (Asia/Ho_Chi_Minh): {availability_time.isoformat()}")
    print(f"Availability + 10 minutes: {ready_time.isoformat()}")
    print(f"Past availability + 10 minutes: {now >= ready_time}")

    latitudes = ",".join(str(latitude) for _, latitude, _ in LOCATIONS)
    longitudes = ",".join(str(longitude) for _, _, longitude in LOCATIONS)
    data_url = (
        f"{DATA_URL}?latitude={latitudes}&longitude={longitudes}"
        "&hourly=pm2_5,pm10,us_aqi,european_aqi"
        "&forecast_days=1&domains=cams_global&timezone=Asia%2FHo_Chi_Minh"
    )
    results = fetch_json(data_url)
    if not isinstance(results, list) or len(results) != len(LOCATIONS):
        raise ValueError("Expected one response per location")

    hourly_hashes = []
    for (name, latitude, longitude), result in zip(LOCATIONS, results, strict=True):
        hourly = result["hourly"]
        # Hash only hourly content because request timing can change other response fields.
        hourly_bytes = json.dumps(hourly, sort_keys=True, separators=(",", ":")).encode("utf-8")
        hourly_hash = hashlib.sha256(hourly_bytes).hexdigest()[:12]
        hourly_hashes.append(hourly_hash)

        # Response coordinates can be rounded without identifying the source model cell.
        grid_latitude = nearest_grid_coordinate(latitude, -90.0)
        grid_longitude = nearest_grid_coordinate(longitude, -180.0)
        print(f"\n{name} ({latitude}, {longitude})")
        print(f"  Response keys: {list(result)}")
        print(f"  Response coordinates: {result['latitude']}, {result['longitude']}")
        print(f"  Nearest 0.4° grid cell: {grid_latitude}, {grid_longitude}")
        print(f"  Hourly SHA-256: {hourly_hash}")
        print("  First hourly rows:")
        for index, timestamp in enumerate(hourly["time"][:4]):
            print(
                f"    {timestamp}: pm2_5={hourly['pm2_5'][index]}, "
                f"pm10={hourly['pm10'][index]}, us_aqi={hourly['us_aqi'][index]}, "
                f"european_aqi={hourly['european_aqi'][index]}"
            )

    print(f"\nAll five hourly hashes distinct: {len(set(hourly_hashes)) == len(LOCATIONS)}")


if __name__ == "__main__":
    main()
