from app.core.settings import get_settings


def test_get_settings_is_cached_until_cache_clear(monkeypatch) -> None:
    original = get_settings()
    monkeypatch.setenv("AIRQ_SNAPSHOT_MAX_PAST_DAYS", "7")
    try:
        assert get_settings() is original
        assert get_settings().snapshot_max_past_days == original.snapshot_max_past_days

        get_settings.cache_clear()
        assert get_settings() is not original
        assert get_settings().snapshot_max_past_days == 7
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()
