from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache

class Settings(BaseSettings):
    app_name: str = "Store Price API"
    debug: bool = True
    cache_ttl_hours: int = 24
    request_timeout_minutes: int = 10
    immediate_timeout_seconds: int = 60
    database_url: str = "sqlite:///price_scraper.db"
    scraper_api_key: str = ""
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="allow"  # Allow extra fields in the settings
    )

@lru_cache()
def get_settings():
    return Settings() 