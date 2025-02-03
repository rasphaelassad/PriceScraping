"""Application configuration settings."""
from pydantic_settings import BaseSettings
from typing import Optional
from functools import lru_cache

class Settings(BaseSettings):
    """Application settings."""
    
    # API settings
    scraper_api_key: str
    
    # ScraperAPI Configuration
    scraper_api_base_url: str = "https://async.scraperapi.com/jobs"  # async endpoint
    scraper_api_retry_interval: int = 10  # seconds
    scraper_api_max_retries: int = 6  # 1 minute with 10 second intervals
    scraper_api_timeout: int = 60  # seconds
    
    # Database settings
    database_url: str
    
    # Debug settings
    debug: bool = False
    
    # SQLAlchemy settings
    sqlalchemy_silence_uber_warning: Optional[str] = None

    class Config:
        """Pydantic config."""
        env_file = ".env"
        case_sensitive = False
        extra = "allow"  # Allow extra fields

@lru_cache()
def get_settings() -> Settings:
    """Get cached settings."""
    return Settings() 