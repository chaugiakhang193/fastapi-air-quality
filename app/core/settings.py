from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AIRQ_")

    open_meteo_air_quality_url: str = "https://air-quality-api.open-meteo.com/v1/air-quality"
    open_meteo_timeout_seconds: float = 10.0


@lru_cache
def get_settings() -> Settings:
    # lru_cache keeps one Settings instance per process. Tests that need a
    # different value must call get_settings.cache_clear() first.
    return Settings()
