from app.schemas.location import Location

# Coordinates are the geocoding origins used to seed the future `location`
# table, not the API's response coordinates — those are rounded and do not
# identify which 0.4-degree grid cell backs the data
# (see labs/00_probe_open_meteo.py). All five sit in Vietnam's civil UTC+07:00,
# stored explicitly rather than trusting the API's `timezone=auto`, which
# returns "Asia/Bangkok" for the northern locations.
SEED_LOCATIONS: list[Location] = [
    Location(
        code="hanoi",
        name="Hà Nội",
        latitude=21.0245,
        longitude=105.84117,
        timezone="Asia/Ho_Chi_Minh",
    ),
    Location(
        code="hcmc",
        name="Thành phố Hồ Chí Minh",
        latitude=10.82302,
        longitude=106.62965,
        timezone="Asia/Ho_Chi_Minh",
    ),
    Location(
        code="danang",
        name="Đà Nẵng",
        latitude=16.06778,
        longitude=108.22083,
        timezone="Asia/Ho_Chi_Minh",
    ),
    Location(
        code="dienbienphu",
        name="Điện Biên Phủ",
        latitude=21.38602,
        longitude=103.02301,
        timezone="Asia/Ho_Chi_Minh",
    ),
    Location(
        code="dalat",
        name="Đà Lạt",
        latitude=11.94646,
        longitude=108.44193,
        timezone="Asia/Ho_Chi_Minh",
    ),
]

_BY_CODE = {location.code: location for location in SEED_LOCATIONS}


def get_location(code: str) -> Location | None:
    return _BY_CODE.get(code)
