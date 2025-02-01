from pydantic_settings import BaseSettings
from functools import lru_cache
import os

class Settings(BaseSettings):
    """Application settings."""
    
    # API Keys
    scraper_api_key: str = os.getenv("SCRAPER_API_KEY", "")
    
    # API Configuration
    api_timeout: int = 30  # seconds
    max_retries: int = 3
    
    # Scraping Configuration
    max_urls_per_request: int = 10
    max_scrape_time: int = 60  # seconds
    
    class Config:
        env_file = ".env"

@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings() 