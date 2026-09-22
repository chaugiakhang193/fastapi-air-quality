from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AirReadingRow(Base):
    __tablename__ = "air_reading"

    location_id: Mapped[int] = mapped_column(ForeignKey("location.id"), primary_key=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    pm2_5: Mapped[float | None] = mapped_column(Float, nullable=True)
    pm10: Mapped[float | None] = mapped_column(Float, nullable=True)
    us_aqi: Mapped[int | None] = mapped_column(Integer, nullable=True)
    european_aqi: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model_run_id: Mapped[int] = mapped_column(ForeignKey("model_run.id"))
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
