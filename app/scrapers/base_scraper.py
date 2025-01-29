from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Literal, Any, Tuple
import logging
import httpx
import time
import os
import asyncio
import traceback
from dotenv import load_dotenv
from datetime import datetime, timezone
from app.core.config import get_settings
from app.schemas.request_schemas import ensure_utc_datetime
from fastapi import HTTPException
import aiohttp
import uuid

# Load environment variables from .env file
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BaseScraper(ABC):
    """Base class for all store-specific scrapers."""

    def __init__(self, mode: str = "batch_async"):
        """
        Initialize the scraper.
        
        Args:
            mode: Either "batch_async" for batch processing or "async" for individual concurrent requests
        """
        self.settings = get_settings()
        self.api_key = self.settings.scraper_api_key
        if not self.api_key:
            logger.warning("SCRAPER_API_KEY not set. Using mock data for testing.")
        self.scraper_config = self.get_scraper_config()
        self.mode = mode
        self.base_url = "http://api.scraperapi.com"
        self.status_base_url = "https://api.scraperapi.com/status"
        self.store_name = None
        logger.info(f"Initialized {self.__class__.__name__} in {mode} mode")

    @abstractmethod
    def get_scraper_config(self) -> Dict[str, Any]:
        """
        Return scraper configuration for the specific store.
        
        Returns:
            A dictionary containing scraper configuration.
        """
        pass

    @abstractmethod
    async def extract_product_info(self, html: str, url: str) -> Optional[Dict[str, Any]]:
        """
        Extract all product information from HTML content.
        
        Args:
            html: The HTML content to extract information from.
            url: The URL the content was fetched from.
            
        Returns:
            A dictionary containing product information, or None if extraction failed.
        """
        pass

    async def get_raw_content(self, urls: List[str]) -> Dict[str, Any]:
        """Get raw content for URLs."""
        try:
            tasks = []
            url_mapping = {}
            
            for url in urls:
                api_url = self.transform_url(url)
                url_mapping[api_url] = url
                tasks.append(self._fetch_url(api_url))
                
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            if len(urls) == 1:
                result = results[0]
                if isinstance(result, Exception):
                    raise result
                return {"html": result["content"]}
            
            response = {}
            for api_url, result in zip(url_mapping.keys(), results):
                original_url = url_mapping[api_url]
                if isinstance(result, Exception):
                    response[original_url] = {"error": str(result)}
                else:
                    response[original_url] = {"html": result["content"]}
            return response
            
        except Exception as e:
            logger.error(f"Error in get_raw_content: {e}")
            raise HTTPException(status_code=400, detail=str(e))

    async def _fetch_url(self, url: str) -> Dict[str, Any]:
        """Fetch URL content with ScraperAPI using scraper configuration."""
        config = self.get_scraper_config()
        try:
            async with aiohttp.ClientSession() as session:
                params = {
                    'api_key': self.api_key,
                    'url': url,
                    'premium': 'true',
                    'country': config.get('country', 'us'),
                    'keep_headers': str(config.get('keepHeaders', True)).lower(),
                    'render': str(self.store_name in self.get_javascript_required_stores()).lower()
                }
                
                headers = config.get('headers', {})
                logger.info(f"Fetching URL with ScraperAPI: {url}")
                
                async with session.get(self.base_url, params=params, headers=headers) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"ScraperAPI error: {error_text}")
                        raise HTTPException(status_code=response.status, detail=error_text)
                    
                    job_id = response.headers.get('X-ScraperAPI-JobId')
                    status_url = f"{self.status_base_url}/{job_id}" if job_id else None
                    
                    content = await response.text()
                    logger.debug(f"Received response content: {content[:200]}...")
                    
                    return {
                        "content": content,
                        "job_id": job_id,
                        "scraper_status_url": status_url,
                        "start_time": datetime.now(timezone.utc)
                    }
        except Exception as e:
            logger.error(f"Error fetching URL {url}: {str(e)}")
            logger.error(traceback.format_exc())
            raise

    def get_javascript_required_stores(self) -> set:
        """Return set of store names that require JavaScript rendering."""
        return {'walmart', 'costco', 'chefstore'}

    async def get_prices(self, urls: List[str]) -> Dict[str, Any]:
        """Get prices for multiple URLs using the configured mode."""
        if self.mode == "batch_async":
            return await self._get_prices_batch(urls)
        else:
            return await self._get_prices_concurrent(urls)

    async def _get_prices_batch(self, urls: List[str]) -> Dict[str, Any]:
        """Get prices in batch mode. Override in subclass if batch mode is supported."""
        raise NotImplementedError("Batch mode not implemented for this scraper")

    async def _get_prices_concurrent(self, urls: List[str]) -> Dict[str, Any]:
        """Get prices using concurrent individual requests."""
        tasks = [self.get_price(url) for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        response = {}
        for url, result in zip(urls, results):
            if isinstance(result, Exception):
                response[url] = {
                    "request_status": {
                        "status": "failed",
                        "error_message": str(result),
                        "start_time": datetime.now(timezone.utc),
                        "elapsed_time_seconds": 0.0,
                        "job_id": str(uuid.uuid4())
                    }
                }
            else:
                response[url] = result
        return response

    async def get_price(self, url: str) -> Dict[str, Any]:
        """Get price for a single URL. Override in subclass."""
        raise NotImplementedError("get_price not implemented for this scraper")

    def transform_url(self, url: str) -> str:
        """Transform product detail URL to API URL. Override in subclass."""
        return url

    def standardize_output(self, product_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Standardize the product information output.
        
        Args:
            product_info: The raw product information.
            
        Returns:
            A dictionary containing standardized product information.
        """
        try:
            standardized = {
                "store": product_info.get("store", "").lower(),
                "url": product_info.get("url", ""),
                "name": product_info.get("name", ""),
                "price": float(product_info.get("price")) if product_info.get("price") is not None else None,
                "price_string": product_info.get("price_string"),
                "price_per_unit": float(product_info.get("price_per_unit")) if product_info.get("price_per_unit") is not None else None,
                "price_per_unit_string": product_info.get("price_per_unit_string"),
                "store_id": product_info.get("store_id"),
                "store_address": product_info.get("store_address"),
                "store_zip": product_info.get("store_zip"),
                "brand": product_info.get("brand"),
                "sku": product_info.get("sku"),
                "category": product_info.get("category"),
                "timestamp": ensure_utc_datetime(product_info.get("timestamp", datetime.now(timezone.utc)))
            }
            
            # Validate numeric fields
            if standardized["price"] is not None and standardized["price"] < 0:
                logger.warning(f"Negative price found: {standardized['price']}")
                standardized["price"] = None
                standardized["price_string"] = None
                
            if standardized["price_per_unit"] is not None and standardized["price_per_unit"] < 0:
                logger.warning(f"Negative price per unit found: {standardized['price_per_unit']}")
                standardized["price_per_unit"] = None
                standardized["price_per_unit_string"] = None
            
            return standardized
            
        except Exception as e:
            logger.error(f"Error standardizing output: {e}")
            logger.error(traceback.format_exc())
            return product_info  # Return original on error