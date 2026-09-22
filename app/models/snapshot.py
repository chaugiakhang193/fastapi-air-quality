from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class SnapshotRow(Base):
    __tablename__ = "snapshot"
    __table_args__ = (
        UniqueConstraint("model_run_id", "location_id", name="uq_snapshot_model_run_location"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    model_run_id: Mapped[int] = mapped_column(ForeignKey("model_run.id"))
    location_id: Mapped[int] = mapped_column(ForeignKey("location.id"))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict] = mapped_column(JSONB)
