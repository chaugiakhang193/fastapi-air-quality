from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_pascal


class Location(BaseModel):
    # populate_by_name=True is soft-deprecated since Pydantic 2.11 (see
    # pydantic._internal._config.ConfigDict.populate_by_name docstring);
    # validate_by_name + validate_by_alias is the documented replacement.
    model_config = ConfigDict(
        alias_generator=to_pascal, validate_by_name=True, validate_by_alias=True
    )

    code: str
    name: str
    latitude: float
    longitude: float
    timezone: str
