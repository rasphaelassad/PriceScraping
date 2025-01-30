from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Literal, Any
import logging
import httpx
import time
import os
import asyncio
from dotenv import load_dotenv
from datetime import datetime, timezone
from app.core.config import get_settings
from app.schemas.request_schemas import ensure_utc_datetime
from fastapi import HTTPException
import aiohttp
import uuid

# Load environment variables from .env file
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class BaseScraper(ABC):
    """Base class for all store-specific scrapers."""

    TIMEOUT_MINUTES = 10  # Timeout after 10 minutes
    
    def __init__(self, mode: Literal["batch", "async"] = "batch"):
        """
        Initialize the scraper.
        
        Args:
            mode: Either "batch" for batch processing or "async" for individual concurrent requests
        """
        self.settings = get_settings()
        self.api_key = self.settings.scraper_api_key
        self.mode = mode
        self.base_url = "https://async.scraperapi.com/jobs"
        self.batch_url = "https://async.scraperapi.com/batchjobs"
        self.store_name = None
        logger.info(f"Initialized {self.__class__.__name__} in {mode} mode")

    @abstractmethod
    def get_scraper_config(self) -> Dict:
        """
        Return scraper configuration for the specific store.
        Must be implemented by child classes.
        
        Returns:
            Dict: Configuration parameters for the scraper
        """
        pass

    @abstractmethod
    async def extract_product_info(self, html: str, url: str) -> Dict:
        """
        Extract all product information from HTML content.
        Must be implemented by child classes.
        
        Args:
            html (str): Raw HTML content
            url (str): Product URL
            
        Returns:
            Dict: Extracted product information
        """
        pass

    async def get_raw_content(self, urls: List[str]) -> Dict[str, Dict]:
        """Get raw HTML/JSON content for URLs without processing"""
        url_strings = [str(url) for url in urls]
        results = {}
        
        async with httpx.AsyncClient(verify=False) as client:
            try:
                if self.mode == "batch":
                    results = await self._get_raw_batch(url_strings, client)
                else:
                    tasks = [self._get_raw_single(url, client) for url in url_strings]
                    task_results = await asyncio.gather(*tasks)
                    results = dict(zip(url_strings, task_results))
            except Exception as e:
                logger.error(f"Error in get_raw_content: {str(e)}")
                results = {url: {
                    "error": str(e),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                } for url in url_strings}
                
        return results

    async def _get_raw_single(self, url: str, client: httpx.AsyncClient) -> Dict:
        """Get raw content for a single URL"""
        try:
            config = self.get_scraper_config()
            # Submit job to ScraperAPI
            payload = {
                "url": url,
                "apiKey": self.api_key,
                "country_code": config.get('country', 'us'),
                "render": str(self.store_name in self.get_javascript_required_stores()).lower(),
                **config
            }
            
            logger.info(f"Fetching URL with ScraperAPI: {url}")
            
            response = await client.post(self.base_url, json=payload)
            if response.status_code != 200:
                return {
                    "error": f"API request failed with status {response.status_code}",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }

            job_data = response.json()
            job_id = job_data.get('id')
            status_url = job_data.get('statusUrl')

            if not job_id:
                return {
                    "error": "No job ID received",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }

            # Poll for job completion
            start_time = time.time()
            while True:
                if (time.time() - start_time) / 60 >= self.TIMEOUT_MINUTES:
                    return {
                        "error": "Job timed out",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }

                status_response = await client.get(status_url)
                status_data = status_response.json()
                status = status_data.get('status')

                if status == 'failed':
                    return {
                        "error": "Job failed",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                elif status == 'finished':
                    html = status_data.get('response', {}).get('body')
                    if html:
                        return {
                            "content": html,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "start_time": datetime.now(timezone.utc)
                        }
                    else:
                        return {
                            "error": "No HTML content in response",
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        }

                await asyncio.sleep(5)  # Wait before next poll

        except Exception as e:
            return {
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

    async def _get_raw_batch(self, urls: List[str], client: httpx.AsyncClient) -> Dict[str, Dict]:
        """Get raw content for multiple URLs using batch processing"""
        try:
            payload = {
                "urls": urls,
                "apiKey": self.api_key,
                "apiParams": self.get_scraper_config()
            }

            response = await client.post(self.batch_url, json=payload)
            if response.status_code != 200:
                return {url: {
                    "error": f"Batch API request failed with status {response.status_code}",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                } for url in urls}

            jobs = response.json()
            job_statuses = {job['id']: {'status': 'running', 'url': job['url'], 'statusUrl': job['statusUrl']} for job in jobs}
            results = {}
            start_time = time.time()

            while any(status['status'] == 'running' for status in job_statuses.values()):
                if (time.time() - start_time) / 60 >= self.TIMEOUT_MINUTES:
                    for job_info in job_statuses.values():
                        if job_info['status'] == 'running':
                            results[job_info['url']] = {
                                "error": "Job timed out",
                                "timestamp": datetime.now(timezone.utc).isoformat()
                            }
                    break

                for job_id, job_info in job_statuses.items():
                    if job_info['status'] == 'running':
                        status_response = await client.get(job_info['statusUrl'])
                        status_data = status_response.json()
                        current_status = status_data.get('status')
                        
                        if current_status == 'failed':
                            job_info['status'] = 'failed'
                            results[job_info['url']] = {
                                "error": "Job failed",
                                "timestamp": datetime.now(timezone.utc).isoformat()
                            }
                        elif current_status == 'finished':
                            job_info['status'] = 'finished'
                            html = status_data.get('response', {}).get('body')
                            if html:
                                results[job_info['url']] = {
                                    "content": html,
                                    "timestamp": datetime.now(timezone.utc).isoformat()
                                }
                            else:
                                results[job_info['url']] = {
                                    "error": "No HTML content in response",
                                    "timestamp": datetime.now(timezone.utc).isoformat()
                                }

                await asyncio.sleep(5)

            # Fill in any missing results
            for url in urls:
                if url not in results:
                    results[url] = {
                        "error": "Job processing failed",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }

            return results

        except Exception as e:
            return {url: {
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            } for url in urls}

    def get_javascript_required_stores(self) -> set:
        """Return set of store names that require JavaScript rendering."""
        return {'walmart', 'costco', 'chefstore'}

    async def get_price(self, url: str) -> Dict[str, Any]:
        """Get price for a single URL. Override in subclass."""
        raise NotImplementedError("get_price not implemented for this scraper")

    def transform_url(self, url: str) -> str:
        """Transform product detail URL to API URL. Override in subclass."""
        return url

    def standardize_output(self, product_info: Dict) -> Optional[Dict]:
        """
        Standardize the output format across all scrapers
        
        Args:
            product_info (Dict): Raw product information
            
        Returns:
            Optional[Dict]: Standardized product info or None if invalid
        """
        if not product_info:
            return None
        
        try:
            standardized = {
                "store": str(product_info.get("store", "")),
                "url": str(product_info.get("url", "")),
                "name": str(product_info.get("name", "")),
                "price": float(product_info["price"]) if product_info.get("price") not in [None, "", "None"] else None,
                "price_string": str(product_info.get("price_string", "")) or None,
                "price_per_unit": float(product_info.get("price_per_unit")) if product_info.get("price_per_unit") not in [None, "", "None"] else None,
                "price_per_unit_string": str(product_info.get("price_per_unit_string", "")) or None,
                "store_id": str(product_info.get("store_id", "")) or None,
                "store_address": str(product_info.get("store_address", "")) or None,
                "store_zip": str(product_info.get("store_zip", "")) or None,
                "brand": str(product_info.get("brand", "")) or None,
                "sku": str(product_info.get("sku", "")) or None,
                "category": str(product_info.get("category", "")) or None
            }
            return standardized
        except Exception as e:
            logger.error(f"Error standardizing output: {str(e)}")
            return None