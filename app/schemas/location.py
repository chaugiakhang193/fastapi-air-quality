from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_pascal


class Location(BaseModel):
    # populate_by_name=True is soft-deprecated since Pydantic 2.11 (see
    # pydantic._internal._config.ConfigDict.populate_by_name docstring);
    # validate_by_name + validate_by_alias is the documented replacement.
    # from_attributes lets model_validate() read a LocationRow directly; the
    # row exposes snake_case attributes, which validate_by_name accepts.
    model_config = ConfigDict(
        alias_generator=to_pascal,
        validate_by_name=True,
        validate_by_alias=True,
        from_attributes=True,
    )

    code: str
    name: str
    latitude: float
    longitude: float
    timezone: str
