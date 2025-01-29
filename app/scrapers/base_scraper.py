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

# Load environment variables from .env file
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BaseScraper(ABC):
    """Base class for all store-specific scrapers."""

    def __init__(self, mode: Literal["batch", "async"] = "batch"):
        """
        Initialize the scraper.
        
        Args:
            mode: The scraping mode to use. Either "batch" or "async".
        """
        self.settings = get_settings()
        self.api_key = self.settings.scraper_api_key
        if not self.api_key:
            logger.warning("SCRAPER_API_KEY not set. Using mock data for testing.")
        self.scraper_config = self.get_scraper_config()
        self.mode = mode
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

    async def get_raw_content(self, urls: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Get raw HTML/JSON content for URLs without processing.
        
        Args:
            urls: List of URLs to fetch content for.
            
        Returns:
            A dictionary mapping URLs to their content or error information.
        """
        if not urls:
            logger.error("No URLs provided")
            return {}

        if not self.api_key:
            # Return mock data for testing
            logger.info("Using mock data (no API key)")
            mock_time = datetime.now(timezone.utc)
            return {url: {
                "content": "<html><body><h1>Mock Data</h1></body></html>",
                "timestamp": mock_time.isoformat()
            } for url in urls}

        url_strings = [str(url) for url in urls]
        results = {}
        
        try:
            async with httpx.AsyncClient(verify=False) as client:
                if self.mode == "batch":
                    results = await self._get_raw_batch(url_strings, client)
                else:
                    tasks = [self._get_raw_single(url, client) for url in url_strings]
                    task_results = await asyncio.gather(*tasks, return_exceptions=True)
                    results = {}
                    for url, result in zip(url_strings, task_results):
                        if isinstance(result, Exception):
                            logger.error(f"Error fetching {url}: {result}")
                            results[url] = {
                                "error": str(result),
                                "timestamp": datetime.now(timezone.utc).isoformat()
                            }
                        else:
                            results[url] = result
        except Exception as e:
            logger.error(f"Error in get_raw_content: {e}")
            logger.error(traceback.format_exc())
            now = datetime.now(timezone.utc)
            for url in url_strings:
                results[url] = {
                    "error": str(e),
                    "timestamp": now.isoformat()
                }
        
        return results

    async def _get_raw_single(self, url: str, client: httpx.AsyncClient) -> Dict[str, Any]:
        """
        Get raw content for a single URL.
        
        Args:
            url: The URL to fetch content for.
            client: The HTTP client to use.
            
        Returns:
            A dictionary containing the content or error information.
        """
        try:
            # Submit job to ScraperAPI
            api_url = "https://async.scraperapi.com/jobs"
            payload = {
                "url": url,
                "apiKey": self.api_key,
                **self.scraper_config
            }
            
            logger.debug(f"Submitting job for {url}")
            response = await client.post(api_url, json=payload)
            if response.status_code != 200:
                now = datetime.now(timezone.utc)
                error_msg = f"API request failed with status {response.status_code}"
                logger.error(f"{error_msg} for {url}")
                return {
                    "error": error_msg,
                    "timestamp": now.isoformat()
                }

            job_data = response.json()
            job_id = job_data.get('id')
            status_url = job_data.get('statusUrl')

            if not job_id or not status_url:
                now = datetime.now(timezone.utc)
                error_msg = "Invalid job response (missing id or statusUrl)"
                logger.error(f"{error_msg} for {url}")
                return {
                    "error": error_msg,
                    "timestamp": now.isoformat()
                }

            logger.debug(f"Job {job_id} submitted for {url}")

            # Poll for job completion
            start_time = time.time()
            while True:
                # Check timeout
                elapsed_time = time.time() - start_time
                if elapsed_time / 60 >= self.settings.request_timeout_minutes:
                    now = datetime.now(timezone.utc)
                    error_msg = f"Job timed out after {elapsed_time:.1f} seconds"
                    logger.error(f"{error_msg} for {url}")
                    return {
                        "error": error_msg,
                        "timestamp": now.isoformat()
                    }

                status_response = await client.get(status_url)
                status_data = status_response.json()
                status = status_data.get('status')

                if status == 'failed':
                    now = datetime.now(timezone.utc)
                    error_msg = status_data.get('error', 'Job failed')
                    logger.error(f"{error_msg} for {url}")
                    return {
                        "error": error_msg,
                        "timestamp": now.isoformat()
                    }
                elif status == 'finished':
                    html = status_data.get('response', {}).get('body')
                    now = datetime.now(timezone.utc)
                    if html:
                        logger.debug(f"Job {job_id} completed for {url}")
                        return {
                            "content": html,
                            "timestamp": now.isoformat()
                        }
                    else:
                        error_msg = "No HTML content in response"
                        logger.error(f"{error_msg} for {url}")
                        return {
                            "error": error_msg,
                            "timestamp": now.isoformat()
                        }

                await asyncio.sleep(5)  # Wait before next poll

        except Exception as e:
            now = datetime.now(timezone.utc)
            logger.error(f"Error fetching {url}: {e}")
            logger.error(traceback.format_exc())
            return {
                "error": str(e),
                "timestamp": now.isoformat()
            }

    async def _get_raw_batch(self, urls: List[str], client: httpx.AsyncClient) -> Dict[str, Dict[str, Any]]:
        """
        Get raw content for multiple URLs in batch mode.
        
        Args:
            urls: List of URLs to fetch content for.
            client: The HTTP client to use.
            
        Returns:
            A dictionary mapping URLs to their content or error information.
        """
        try:
            # Submit all jobs
            job_statuses = {}
            results = {}
            now = datetime.now(timezone.utc)

            for url in urls:
                try:
                    # Submit job to ScraperAPI
                    api_url = "https://async.scraperapi.com/jobs"
                    payload = {
                        "url": url,
                        "apiKey": self.api_key,
                        **self.scraper_config
                    }
                    
                    response = await client.post(api_url, json=payload)
                    if response.status_code != 200:
                        results[url] = {
                            "error": f"API request failed with status {response.status_code}",
                            "timestamp": now.isoformat()
                        }
                        continue

                    job_data = response.json()
                    job_id = job_data.get('id')
                    status_url = job_data.get('statusUrl')

                    if not job_id or not status_url:
                        results[url] = {
                            "error": "Invalid job response (missing id or statusUrl)",
                            "timestamp": now.isoformat()
                        }
                        continue

                    job_statuses[job_id] = {
                        'url': url,
                        'statusUrl': status_url,
                        'status': 'running',
                        'startTime': time.time()
                    }
                    logger.debug(f"Job {job_id} submitted for {url}")

                except Exception as e:
                    logger.error(f"Error submitting job for {url}: {e}")
                    logger.error(traceback.format_exc())
                    results[url] = {
                        "error": str(e),
                        "timestamp": now.isoformat()
                    }

            # Poll for job completion
            while job_statuses:
                # Check for timeouts
                now = datetime.now(timezone.utc)
                timed_out_jobs = []
                for job_id, job_info in job_statuses.items():
                    elapsed_time = time.time() - job_info['startTime']
                    if elapsed_time / 60 >= self.settings.request_timeout_minutes:
                        timed_out_jobs.append(job_id)
                        results[job_info['url']] = {
                            "error": f"Job timed out after {elapsed_time:.1f} seconds",
                            "timestamp": now.isoformat()
                        }

                for job_id in timed_out_jobs:
                    del job_statuses[job_id]

                # Check status of running jobs
                for job_id, job_info in list(job_statuses.items()):
                    if job_info['status'] == 'running':
                        try:
                            status_response = await client.get(job_info['statusUrl'])
                            status_data = status_response.json()
                            current_status = status_data.get('status')
                            
                            if current_status == 'failed':
                                job_info['status'] = 'failed'
                                error_msg = status_data.get('error', 'Job failed')
                                logger.error(f"{error_msg} for {job_info['url']}")
                                results[job_info['url']] = {
                                    "error": error_msg,
                                    "timestamp": now.isoformat()
                                }
                                del job_statuses[job_id]
                            elif current_status == 'finished':
                                job_info['status'] = 'finished'
                                html = status_data.get('response', {}).get('body')
                                if html:
                                    logger.debug(f"Job {job_id} completed for {job_info['url']}")
                                    results[job_info['url']] = {
                                        "content": html,
                                        "timestamp": now.isoformat()
                                    }
                                else:
                                    error_msg = "No HTML content in response"
                                    logger.error(f"{error_msg} for {job_info['url']}")
                                    results[job_info['url']] = {
                                        "error": error_msg,
                                        "timestamp": now.isoformat()
                                    }
                                del job_statuses[job_id]
                        except Exception as e:
                            logger.error(f"Error checking status for {job_info['url']}: {e}")
                            logger.error(traceback.format_exc())
                            results[job_info['url']] = {
                                "error": str(e),
                                "timestamp": now.isoformat()
                            }
                            del job_statuses[job_id]

                if job_statuses:
                    await asyncio.sleep(5)  # Wait before next poll

            return results

        except Exception as e:
            logger.error(f"Error in batch processing: {e}")
            logger.error(traceback.format_exc())
            now = datetime.now(timezone.utc)
            return {url: {
                "error": str(e),
                "timestamp": now.isoformat()
            } for url in urls}

    async def get_prices(self, urls: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Get prices for the given URLs.
        
        Args:
            urls: List of URLs to get prices for.
            
        Returns:
            A dictionary mapping URLs to their product information.
        """
        try:
            if not self.api_key:
                # Return mock data for testing
                logger.info("Using mock data (no API key)")
                mock_time = datetime.now(timezone.utc)
                return {str(url): {
                    "store": self.__class__.__name__.replace("Scraper", "").lower(),
                    "url": str(url),
                    "name": "Mock Product",
                    "price": 9.99,
                    "price_string": "$9.99",
                    "store_id": "MOCK001",
                    "store_address": "123 Mock St",
                    "store_zip": "12345",
                    "brand": "Mock Brand",
                    "sku": "MOCK123",
                    "category": "Mock Category",
                    "timestamp": mock_time
                } for url in urls}

            raw_results = await self.get_raw_content(urls)
            results = {}
            
            for url, raw_result in raw_results.items():
                if "error" in raw_result:
                    logger.error(f"Error getting content for {url}: {raw_result['error']}")
                    continue
                    
                html = raw_result.get("content")
                if not html:
                    logger.error(f"No HTML content for {url}")
                    continue
                    
                try:
                    product_info = await self.extract_product_info(html, url)
                    if product_info:
                        results[url] = self.standardize_output(product_info)
                    else:
                        logger.warning(f"No product info extracted for {url}")
                except Exception as e:
                    logger.error(f"Error extracting product info for {url}: {e}")
                    logger.error(traceback.format_exc())
            
            return results

        except Exception as e:
            logger.error(f"Error in get_prices: {e}")
            logger.error(traceback.format_exc())
            return {}

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