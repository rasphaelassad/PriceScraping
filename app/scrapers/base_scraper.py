from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Literal
import logging
import httpx
import time
import os
import asyncio
from dotenv import load_dotenv
from datetime import datetime, timezone

# Load environment variables from .env file
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BaseScraper(ABC):
    API_KEY = os.environ["SCRAPER_API_KEY"]
    TIMEOUT_MINUTES = 10  # Timeout after 10 minutes
    
    def __init__(self, mode: Literal["batch", "async"] = "batch"):
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
        """Get raw HTML/JSON content for URLs without processing
        Returns a dictionary with URLs as keys and dictionaries containing content/error and timestamp as values
        """
        url_strings = [str(url) for url in urls]
        results = {}
        
        async with httpx.AsyncClient(verify=False) as client:
            if self.mode == "batch":
                # Use batch processing for multiple URLs
                results = await self._get_raw_batch(url_strings, client)
            else:
                # Process URLs individually
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
                "apiKey": self.API_KEY,
                **self.scraper_config
            }
            
            response = await client.post(api_url, json=payload)
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
                # Check timeout
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
                            "timestamp": datetime.now(timezone.utc).isoformat()
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
            # Submit batch job
            api_url = "https://async.scraperapi.com/batchjobs"
            payload = {
                "urls": urls,
                "apiKey": self.API_KEY,
                "apiParams": self.scraper_config
            }

            response = await client.post(api_url, json=payload)
            if response.status_code != 200:
                return {url: {
                    "error": f"Batch API request failed with status {response.status_code}",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                } for url in urls}

            jobs = response.json()
            job_statuses = {job['id']: {'status': 'running', 'url': job['url'], 'statusUrl': job['statusUrl']} for job in jobs}
            results = {}
            start_time = time.time()

            # Poll for all jobs completion
            while any(status['status'] == 'running' for status in job_statuses.values()):
                if (time.time() - start_time) / 60 >= self.TIMEOUT_MINUTES:
                    # Handle timeout for remaining jobs
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

    def standardize_output(self, product_info: Dict) -> Dict:
        """Standardize the output format across all scrapers"""
        if not product_info:
            return None

        logger.debug(f"Standardizing output - input timestamp: {product_info.get('timestamp')}, type: {type(product_info.get('timestamp'))}")
        
        # Ensure timestamp is timezone-aware
        timestamp = product_info.get("timestamp")
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)
        elif isinstance(timestamp, str):
            try:
                timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                if timestamp.tzinfo is None:
                    timestamp = timestamp.replace(tzinfo=timezone.utc)
                timestamp = timestamp.astimezone(timezone.utc)
            except ValueError:
                timestamp = datetime.now(timezone.utc)
        elif isinstance(timestamp, datetime):
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            else:
                timestamp = timestamp.astimezone(timezone.utc)
        else:
            timestamp = datetime.now(timezone.utc)
        
        logger.debug(f"Standardized timestamp: {timestamp}, tzinfo: {timestamp.tzinfo}")

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
            "timestamp": timestamp
        }

        return standardized

    async def get_prices(self, urls: List[str]) -> Dict[str, Dict]:
        """Get product information for multiple URLs"""
        # First get the raw content
        raw_results = await self.get_raw_content(urls)
        
        # Process the raw content to extract product information
        processed_results = {}
        for url, result in raw_results.items():
            if "content" in result:
                try:
                    # Parse timestamp from raw result
                    logger.debug(f"Raw timestamp: {result.get('timestamp')}, type: {type(result.get('timestamp'))}")
                    raw_timestamp = result.get("timestamp")
                    if raw_timestamp is None:
                        timestamp = datetime.now(timezone.utc)
                    elif isinstance(raw_timestamp, str):
                        try:
                            timestamp = datetime.fromisoformat(raw_timestamp.replace('Z', '+00:00'))
                            if timestamp.tzinfo is None:
                                timestamp = timestamp.replace(tzinfo=timezone.utc)
                            timestamp = timestamp.astimezone(timezone.utc)
                        except ValueError:
                            timestamp = datetime.now(timezone.utc)
                    elif isinstance(raw_timestamp, datetime):
                        if raw_timestamp.tzinfo is None:
                            timestamp = raw_timestamp.replace(tzinfo=timezone.utc)
                        else:
                            timestamp = raw_timestamp.astimezone(timezone.utc)
                    else:
                        timestamp = datetime.now(timezone.utc)
                    
                    logger.debug(f"Parsed timestamp: {timestamp}, tzinfo: {timestamp.tzinfo}")
                    
                    # Extract product info
                    product_info = await self.extract_product_info(result["content"], url)
                    if product_info:
                        # Ensure product info has the timestamp
                        product_info["timestamp"] = timestamp
                        logger.debug(f"Product info timestamp: {product_info['timestamp']}, tzinfo: {product_info['timestamp'].tzinfo}")
                        processed_results[url] = self.standardize_output(product_info)
                    else:
                        processed_results[url] = None
                except Exception as e:
                    logger.error(f"Error processing URL {url}: {str(e)}")
                    processed_results[url] = None
            else:
                processed_results[url] = None
                
        return processed_results