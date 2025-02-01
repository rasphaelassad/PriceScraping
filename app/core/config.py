from pydantic import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    """Application settings."""
    
    # API Keys
    scraper_api_key: str  # This will raise an error if not provided
    
    # API Configuration
    api_timeout: int = 30  # seconds
    max_retries: int = 3
    
    # Scraping Configuration
    max_urls_per_request: int = 10
    max_scrape_time: int = 60  # seconds
    
    class Config:
        env_file = ".env"
        env_file_encoding = 'utf-8'

@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings() 