from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Type
import logging
import httpx
import asyncio
from datetime import datetime, timezone
import uuid
from app.core.config import get_settings
import re

logger = logging.getLogger(__name__)

class BaseScraper(ABC):
    """Base class for all store-specific scrapers."""
    
    # Store name and URL pattern - must be set in subclasses
    store_name: str = ""
    url_pattern: str = ""
    
    def __init__(self):
        """Initialize the scraper with API key and common settings."""
        if not self.store_name or not self.url_pattern:
            raise ValueError("Scraper must define store_name and url_pattern")
            
        self.settings = get_settings()
        self.api_key = self.settings.scraper_api_key
        if not self.api_key:
            raise ValueError("SCRAPER_API_KEY environment variable not set")
        self.base_url = "https://api.scraperapi.com/async"
        self.status_url = "https://api.scraperapi.com/status"
        self.max_retries = 6  # 1 minute with 10 second intervals
        self.retry_interval = 10  # seconds

    @classmethod
    def can_handle_url(cls, url: str) -> bool:
        """Check if this scraper can handle the given URL."""
        if not cls.url_pattern:
            raise NotImplementedError("url_pattern must be set in scraper subclass")
        return bool(re.search(cls.url_pattern, url, re.IGNORECASE))

    @classmethod
    def get_scraper_for_url(cls, url: str, available_scrapers: list[Type['BaseScraper']]) -> Optional[Type['BaseScraper']]:
        """Find the appropriate scraper class for a URL."""
        for scraper_class in available_scrapers:
            if scraper_class.can_handle_url(url):
                return scraper_class
        return None

    @abstractmethod
    def get_scraper_config(self) -> dict:
        """Get store-specific scraper configuration."""
        pass

    @abstractmethod
    async def extract_product_info(self, html: str, url: str) -> Optional[Dict]:
        """Extract product information from HTML content."""
        pass

    def transform_url(self, url: str) -> str:
        """Transform URL if needed. Override in store-specific scrapers if needed."""
        return url

    async def fetch_content(self, url: str) -> Optional[str]:
        """Fetch page content asynchronously."""
        transformed_url = self.transform_url(url)
        params = {
            "api_key": self.api_key,
            "url": transformed_url,
            **self.get_scraper_config()
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(self.base_url, params=params)
                response.raise_for_status()
                return response.text
            except httpx.HTTPError as e:
                logger.error(f"HTTP error while fetching {url}: {e}")
                return None

    async def get_price(self, url: str) -> Dict[str, Any]:
        start_time = datetime.now(timezone.utc)
        html = await self.fetch_content(url)

        if html is None:
            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
            return {
                "request_status": {
                    "status": "failed",
                    "start_time": start_time.isoformat(),
                    "elapsed_time_seconds": elapsed,
                    "error_message": "Failed to fetch content"
                }
            }

        product_info = await self.extract_product_info(html, url)
        elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()

        if product_info is None:
            return {
                "request_status": {
                    "status": "failed",
                    "start_time": start_time.isoformat(),
                    "elapsed_time_seconds": elapsed,
                    "error_message": "Failed to extract product information"
                }
            }

        return {
            "request_status": {
                "status": "completed",
                "start_time": start_time.isoformat(),
                "elapsed_time_seconds": elapsed,
            },
            "result": product_info
        } 