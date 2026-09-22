from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AIRQ_",
        env_file=".env",
        extra="ignore",
    )

    open_meteo_air_quality_url: str = "https://air-quality-api.open-meteo.com/v1/air-quality"
    open_meteo_meta_url: str = (
        "https://air-quality-api.open-meteo.com/data/cams_global/static/meta.json"
    )
    open_meteo_model: str = "cams_global"
    open_meteo_timeout_seconds: float = 10.0

    # These legacy variable names are kept for compatibility with .env.example.
    database_url: str = Field(validation_alias="DATABASE_URL")
    snapshot_api_key: str = Field(validation_alias="SNAPSHOT_API_KEY")

    snapshot_max_past_days: int = 92
    snapshot_min_available_delay_minutes: int = 10


@lru_cache
def get_settings() -> Settings:
    # lru_cache keeps one Settings instance per process. Tests that need a
    # different value must call get_settings.cache_clear() first.
    return Settings()
