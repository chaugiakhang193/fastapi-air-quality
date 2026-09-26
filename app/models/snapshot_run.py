from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class SnapshotRunStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    NO_NEW_DATA = "no_new_data"
    FAILED = "failed"


class SnapshotRunRow(Base):
    __tablename__ = "snapshot_run"

    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Store status as a varchar so adding a state does not require altering a Postgres enum type.
    # values_callable persists each member's value ("running") instead of SQLAlchemy's
    # default of the member's name ("RUNNING"). create_constraint adds the CHECK that
    # migration 0002 creates, so tables built by create_all() in tests enforce it too.
    status: Mapped[SnapshotRunStatus] = mapped_column(
        Enum(
            SnapshotRunStatus,
            native_enum=False,
            length=20,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
            create_constraint=True,
            name="ck_snapshot_run_status",
        )
    )
    model_run_id: Mapped[int | None] = mapped_column(ForeignKey("model_run.id"), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(String(500), nullable=True)
