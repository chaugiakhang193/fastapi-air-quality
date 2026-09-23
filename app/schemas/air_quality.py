from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_pascal


def split_locations(value: str) -> list[str]:
    # Stored codes are lowercase, and a repeated code would make /hourly ask
    # Open-Meteo for the same coordinate twice, so codes are lowercased and
    # de-duplicated here while keeping first-seen order.
    codes = [code.strip().lower() for code in value.split(",") if code.strip()]
    if not codes:
        raise ValueError("Locations must contain at least one code")
    return list(dict.fromkeys(codes))


# Shared by GET /air-quality/hourly and GET /air-quality/daily — both need
# "?Locations=hanoi,hcmc" split into individual codes the same way.
LocationCodes = Annotated[str, AfterValidator(split_locations)]


class HourlyReading(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_pascal, validate_by_name=True, validate_by_alias=True
    )

    time: str
    # to_pascal("pm2_5") produces "Pm25" (drops the underscore between two
    # digits) — overridden here to keep the digit-underscore-digit shape
    # Open-Meteo itself uses.
    pm2_5: float | None = Field(default=None, alias="Pm2_5")
    pm10: float | None = None
    us_aqi: int | None = None
    european_aqi: int | None = None


class LocationHourly(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_pascal, validate_by_name=True, validate_by_alias=True
    )

    code: str
    name: str
    hourly: list[HourlyReading]


class DailyEntry(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_pascal, validate_by_name=True, validate_by_alias=True
    )

    date: str
    hours_count: int
    forecast_hours: int
    avg_pm2_5: float | None = Field(default=None, alias="AvgPm2_5")
    avg_pm10: float | None = None
    avg_us_aqi: float | None = None
    avg_european_aqi: float | None = None
    exceeds_who_pm2_5: bool | None = Field(default=None, alias="ExceedsWhoPm2_5")
    exceeds_who_pm10: bool | None = None


class LocationDaily(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_pascal, validate_by_name=True, validate_by_alias=True
    )

    code: str
    name: str
    days: list[DailyEntry]
