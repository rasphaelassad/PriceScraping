from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Literal
import logging
import httpx
import time
import os
import asyncio
from dotenv import load_dotenv
from datetime import datetime, timezone
from app.core.config import get_settings
from app.schemas.request_schemas import ensure_utc_datetime

# Load environment variables from .env file
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BaseScraper(ABC):
    def __init__(self, mode: Literal["batch", "async"] = "batch"):
        self.settings = get_settings()
        self.api_key = self.settings.scraper_api_key
        if not self.api_key:
            logger.warning("SCRAPER_API_KEY not set. Using mock data for testing.")
        self.scraper_config = self.get_scraper_config()
        self.mode = mode

    @abstractmethod
    def get_scraper_config(self) -> Dict:
        """Return scraper configuration for the specific store"""
        pass

    @abstractmethod
    async def extract_product_info(self, html: str, url: str) -> Dict:
        """Extract all product information from HTML content"""
        pass

    async def get_raw_content(self, urls: List[str]) -> Dict[str, Dict]:
        """Get raw HTML/JSON content for URLs without processing"""
        if not self.api_key:
            # Return mock data for testing
            mock_time = datetime.now(timezone.utc)
            return {url: {
                "content": "<html><body><h1>Mock Data</h1></body></html>",
                "timestamp": mock_time.isoformat()
            } for url in urls}

        url_strings = [str(url) for url in urls]
        results = {}
        
        async with httpx.AsyncClient(verify=False) as client:
            if self.mode == "batch":
                results = await self._get_raw_batch(url_strings, client)
            else:
                tasks = [self._get_raw_single(url, client) for url in url_strings]
                task_results = await asyncio.gather(*tasks)
                results = dict(zip(url_strings, task_results))
        
        return results

    async def _get_raw_single(self, url: str, client: httpx.AsyncClient) -> Dict:
        """Get raw content for a single URL"""
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
                now = datetime.now(timezone.utc)
                return {
                    "error": f"API request failed with status {response.status_code}",
                    "timestamp": now.isoformat()
                }

            job_data = response.json()
            job_id = job_data.get('id')
            status_url = job_data.get('statusUrl')

            if not job_id:
                now = datetime.now(timezone.utc)
                return {
                    "error": "No job ID received",
                    "timestamp": now.isoformat()
                }

            # Poll for job completion
            start_time = time.time()
            while True:
                # Check timeout
                if (time.time() - start_time) / 60 >= self.settings.request_timeout_minutes:
                    now = datetime.now(timezone.utc)
                    return {
                        "error": "Job timed out",
                        "timestamp": now.isoformat()
                    }

                status_response = await client.get(status_url)
                status_data = status_response.json()
                status = status_data.get('status')

                if status == 'failed':
                    now = datetime.now(timezone.utc)
                    return {
                        "error": "Job failed",
                        "timestamp": now.isoformat()
                    }
                elif status == 'finished':
                    html = status_data.get('response', {}).get('body')
                    now = datetime.now(timezone.utc)
                    if html:
                        return {
                            "content": html,
                            "timestamp": now.isoformat()
                        }
                    else:
                        return {
                            "error": "No HTML content in response",
                            "timestamp": now.isoformat()
                        }

                await asyncio.sleep(5)  # Wait before next poll

        except Exception as e:
            now = datetime.now(timezone.utc)
            return {
                "error": str(e),
                "timestamp": now.isoformat()
            }

    async def _get_raw_batch(self, urls: List[str], client: httpx.AsyncClient) -> Dict[str, Dict]:
        """Get raw content for multiple URLs using batch processing"""
        try:
            # Submit batch job
            api_url = "https://async.scraperapi.com/batchjobs"
            payload = {
                "urls": urls,
                "apiKey": self.api_key,
                "apiParams": self.scraper_config
            }

            response = await client.post(api_url, json=payload)
            if response.status_code != 200:
                now = datetime.now(timezone.utc)
                return {url: {
                    "error": f"Batch API request failed with status {response.status_code}",
                    "timestamp": now.isoformat()
                } for url in urls}

            jobs = response.json()
            job_statuses = {job['id']: {'status': 'running', 'url': job['url'], 'statusUrl': job['statusUrl']} for job in jobs}
            results = {}
            start_time = time.time()

            # Poll for all jobs completion
            while any(status['status'] == 'running' for status in job_statuses.values()):
                if (time.time() - start_time) / 60 >= self.settings.request_timeout_minutes:
                    # Handle timeout for remaining jobs
                    now = datetime.now(timezone.utc)
                    for job_info in job_statuses.values():
                        if job_info['status'] == 'running':
                            results[job_info['url']] = {
                                "error": "Job timed out",
                                "timestamp": now.isoformat()
                            }
                    break

                # Check status of running jobs
                for job_id, job_info in job_statuses.items():
                    if job_info['status'] == 'running':
                        status_response = await client.get(job_info['statusUrl'])
                        status_data = status_response.json()
                        current_status = status_data.get('status')
                        now = datetime.now(timezone.utc)
                        
                        if current_status == 'failed':
                            job_info['status'] = 'failed'
                            results[job_info['url']] = {
                                "error": "Job failed",
                                "timestamp": now.isoformat()
                            }
                        elif current_status == 'finished':
                            job_info['status'] = 'finished'
                            html = status_data.get('response', {}).get('body')
                            if html:
                                results[job_info['url']] = {
                                    "content": html,
                                    "timestamp": now.isoformat()
                                }
                            else:
                                results[job_info['url']] = {
                                    "error": "No HTML content in response",
                                    "timestamp": now.isoformat()
                                }

                await asyncio.sleep(5)

            # Fill in any missing results
            now = datetime.now(timezone.utc)
            for url in urls:
                if url not in results:
                    results[url] = {
                        "error": "Job processing failed",
                        "timestamp": now.isoformat()
                    }

            return results

        except Exception as e:
            now = datetime.now(timezone.utc)
            return {url: {
                "error": str(e),
                "timestamp": now.isoformat()
            } for url in urls}

    def standardize_output(self, product_info: Dict) -> Dict:
        """Standardize the output format"""
        now = datetime.now(timezone.utc)
        # Ensure all required fields are present with proper types
        standardized = {
            "store": str(product_info.get("store", "")),
            "url": str(product_info.get("url", "")),
            "name": str(product_info.get("name", "")),
            "price": float(product_info["price"]) if product_info.get("price") is not None else None,
            "price_string": str(product_info.get("price_string")) if product_info.get("price_string") else None,
            "price_per_unit": float(product_info.get("price_per_unit")) if product_info.get("price_per_unit") else None,
            "price_per_unit_string": str(product_info.get("price_per_unit_string")) if product_info.get("price_per_unit_string") else None,
            "store_id": str(product_info.get("store_id")) if product_info.get("store_id") else None,
            "store_address": str(product_info.get("store_address")) if product_info.get("store_address") else None,
            "store_zip": str(product_info.get("store_zip")) if product_info.get("store_zip") else None,
            "brand": str(product_info.get("brand")) if product_info.get("brand") else None,
            "sku": str(product_info.get("sku")) if product_info.get("sku") else None,
            "category": str(product_info.get("category")) if product_info.get("category") else None,
            "timestamp": ensure_utc_datetime(product_info.get("timestamp", now))
        }

        return standardized

    async def get_prices(self, urls: List[str]) -> Dict[str, Dict]:
        """Get prices for the given URLs"""
        try:
            if not self.api_key:
                # Return mock data for testing
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
                except Exception as e:
                    logger.error(f"Error extracting product info for {url}: {str(e)}")
                    
            return results
        except Exception as e:
            logger.error(f"Error in get_prices: {str(e)}")
            raise  # Let the caller handle the error