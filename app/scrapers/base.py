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

    async def check_job_status(self, job_id: str) -> Dict[str, Any]:
        """Check the status of a ScraperAPI job."""
        async with httpx.AsyncClient() as client:
            params = {
                "api_key": self.api_key,
                "job_id": job_id
            }
            response = await client.get(self.status_url, params=params)
            return response.json()

    async def create_scrape_job(self, url: str) -> Dict[str, Any]:
        """Create a new scraping job with ScraperAPI."""
        async with httpx.AsyncClient() as client:
            config = self.get_scraper_config()
            payload = {
                "apiKey": self.api_key,
                "url": self.transform_url(url),
                **config
            }
            response = await client.post(self.base_url, json=payload)
            if response.status_code != 200:
                raise ValueError(f"Failed to create scrape job: {response.text}")
            return response.json()

    async def wait_for_completion(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Wait for a scraping job to complete."""
        for attempt in range(self.max_retries):
            status_data = await self.check_job_status(job_id)
            
            if status_data.get("status") == "finished":
                return status_data.get("response", {})
            elif status_data.get("status") == "failed":
                logger.error(f"Job {job_id} failed: {status_data.get('error')}")
                return None
                
            await asyncio.sleep(self.retry_interval)
            
        logger.error(f"Job {job_id} timed out after {self.max_retries} attempts")
        return None

    async def get_price(self, url: str) -> Dict[str, Any]:
        """Get price information for a URL using ScraperAPI."""
        start_time = datetime.now(timezone.utc)
        job_id = str(uuid.uuid4())
        
        try:
            # Create scraping job
            job_data = await self.create_scrape_job(url)
            job_id = job_data.get("id")
            
            # Wait for completion
            response_data = await self.wait_for_completion(job_id)
            if not response_data:
                return {
                    "request_status": {
                        "status": "failed",
                        "job_id": job_id,
                        "start_time": start_time,
                        "elapsed_time_seconds": (datetime.now(timezone.utc) - start_time).total_seconds(),
                        "error_message": "Scraping job failed or timed out"
                    }
                }
            
            # Extract product info
            html = response_data.get("body", "")
            product_info = await self.extract_product_info(html, url)
            
            if not product_info:
                return {
                    "request_status": {
                        "status": "failed",
                        "job_id": job_id,
                        "start_time": start_time,
                        "elapsed_time_seconds": (datetime.now(timezone.utc) - start_time).total_seconds(),
                        "error_message": "Failed to extract product information"
                    }
                }
            
            return {
                "request_status": {
                    "status": "completed",
                    "job_id": job_id,
                    "start_time": start_time,
                    "elapsed_time_seconds": (datetime.now(timezone.utc) - start_time).total_seconds(),
                },
                "result": product_info
            }
            
        except Exception as e:
            logger.error(f"Error getting price for {url}: {str(e)}")
            return {
                "request_status": {
                    "status": "failed",
                    "job_id": job_id,
                    "start_time": start_time,
                    "elapsed_time_seconds": (datetime.now(timezone.utc) - start_time).total_seconds(),
                    "error_message": str(e)
                }
            } 