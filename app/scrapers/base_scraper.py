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
    API_KEY = os.environ.get("SCRAPER_API_KEY")
    TIMEOUT_MINUTES = 10  # Timeout after 10 minutes
    
    def __init__(self, mode: Literal["batch", "async"] = "batch"):
        if not self.API_KEY:
            raise ValueError("SCRAPER_API_KEY environment variable is not set")
        self.scraper_config = self.get_scraper_config()
        self.mode = mode

    @abstractmethod
    def get_scraper_config(self) -> Dict:
        """Return scraper configuration for the specific store"""
        pass

    @abstractmethod
    async def extract_product_info(self, html: str, url: str) -> Optional[Dict]:
        """Extract all product information from HTML content"""
        pass

    def transform_url(self, url: str) -> str:
        """Optional method to transform URL before scraping. Override if needed."""
        return url

    async def get_prices(self, urls: List[str]) -> Dict[str, Optional[Dict]]:
        """Get prices for multiple URLs"""
        # Transform URLs if needed
        transformed_urls = [self.transform_url(url) for url in urls]
        
        # Get raw content
        raw_content = await self._get_raw_response(transformed_urls)
        
        # Process each URL
        results = {}
        for original_url, transformed_url in zip(urls, transformed_urls):
            if transformed_url not in raw_content:
                results[original_url] = None
                continue
                
            content = raw_content[transformed_url]
            if "error" in content:
                logger.error(f"Error getting content for {original_url}: {content['error']}")
                results[original_url] = None
                continue
                
            try:
                product_info = await self.extract_product_info(content["content"], original_url)
                results[original_url] = product_info
            except Exception as e:
                logger.error(f"Error extracting product info for {original_url}: {str(e)}")
                results[original_url] = None
                
        return results

    async def _get_raw_response(self, urls: List[str]) -> Dict[str, Dict]:
        """Get raw HTML/JSON content for URLs"""
        url_strings = [str(url) for url in urls]
        results = {}
        
        async with httpx.AsyncClient(verify=False) as client:
            if self.mode == "batch" and len(urls) > 1:
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
            status_url = job_data.get('statusUrl')
            if not status_url:
                return {
                    "error": "No status URL received",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }

            # Poll for completion
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
                    result_url = status_data.get('url')
                    if not result_url:
                        return {
                            "error": "No result URL in response",
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        }

                    content_response = await client.get(result_url)
                    if content_response.status_code != 200:
                        return {
                            "error": f"Failed to get content with status {content_response.status_code}",
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        }

                    return {
                        "content": content_response.text,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }

                await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"Error getting raw content for {url}: {str(e)}")
            return {
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

    async def _get_raw_batch(self, urls: List[str], client: httpx.AsyncClient) -> Dict[str, Dict]:
        """Get raw content for multiple URLs in batch"""
        try:
            api_url = "https://async.scraperapi.com/jobs"
            payload = {
                "urls": urls,
                "apiKey": self.API_KEY,
                **self.scraper_config
            }
            
            response = await client.post(api_url, json=payload)
            if response.status_code != 200:
                return {url: {
                    "error": f"API request failed with status {response.status_code}",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                } for url in urls}

            job_data = response.json()
            status_url = job_data.get('statusUrl')
            if not status_url:
                return {url: {
                    "error": "No status URL received",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                } for url in urls}

            # Poll for completion
            start_time = time.time()
            while True:
                if (time.time() - start_time) / 60 >= self.TIMEOUT_MINUTES:
                    return {url: {
                        "error": "Job timed out",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    } for url in urls}

                status_response = await client.get(status_url)
                status_data = status_response.json()
                status = status_data.get('status')

                if status == 'failed':
                    return {url: {
                        "error": "Job failed",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    } for url in urls}
                elif status == 'finished':
                    results = status_data.get('results', {})
                    processed_results = {}
                    
                    for url in urls:
                        result = results.get(url, {})
                        if result.get('status') == 'finished':
                            result_url = result.get('url')
                            if result_url:
                                content_response = await client.get(result_url)
                                if content_response.status_code == 200:
                                    processed_results[url] = {
                                        "content": content_response.text,
                                        "timestamp": datetime.now(timezone.utc).isoformat()
                                    }
                                else:
                                    processed_results[url] = {
                                        "error": f"Failed to get content with status {content_response.status_code}",
                                        "timestamp": datetime.now(timezone.utc).isoformat()
                                    }
                            else:
                                processed_results[url] = {
                                    "error": "No result URL in response",
                                    "timestamp": datetime.now(timezone.utc).isoformat()
                                }
                        else:
                            processed_results[url] = {
                                "error": f"Job failed for URL with status {result.get('status')}",
                                "timestamp": datetime.now(timezone.utc).isoformat()
                            }
                    
                    return processed_results

                await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"Error in batch processing: {str(e)}")
            return {url: {
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            } for url in urls}