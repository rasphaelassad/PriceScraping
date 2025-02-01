"""Application configuration settings."""
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache

class Settings(BaseSettings):
    """Application settings."""
    
    # API Keys
    scraper_api_key: str
    
    # API Configuration
    api_timeout: int = 30  # seconds
    max_retries: int = 3
    
    # Scraping Configuration
    max_urls_per_request: int = 10
    max_scrape_time: int = 60  # seconds
    
    # ScraperAPI Configuration
    scraper_api_base_url: str = "https://api.scraperapi.com"
    scraper_api_async_endpoint: str = "/async"
    scraper_api_status_endpoint: str = "/status"
    scraper_api_retry_interval: int = 10  # seconds
    scraper_api_max_retries: int = 6  # 1 minute with 10 second intervals
    
    # Model configuration
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False
    )

@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings() 