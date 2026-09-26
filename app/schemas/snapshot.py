from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_pascal

from app.models import SnapshotRunStatus


class SnapshotPageQuery(BaseModel):
    # Used as a query parameter model: Limit and BeforeId arrive under their
    # PascalCase aliases, and any other query key is rejected with 422.
    model_config = ConfigDict(
        alias_generator=to_pascal,
        validate_by_name=True,
        validate_by_alias=True,
        extra="forbid",
    )

    limit: int = Field(default=20, ge=1, le=100)
    before_id: int | None = Field(default=None, ge=1)


class SnapshotRunEntry(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_pascal, validate_by_name=True, validate_by_alias=True
    )

    id: int
    started_at: datetime
    finished_at: datetime | None
    status: SnapshotRunStatus
    run_at: datetime | None
    error_code: str | None


class SnapshotRunPage(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_pascal, validate_by_name=True, validate_by_alias=True
    )

    items: list[SnapshotRunEntry]
    next_before_id: int | None
