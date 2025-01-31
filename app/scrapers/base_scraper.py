
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Literal
import logging
import httpx
import time
import os
import asyncio
import json
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BaseScraper(ABC):
    API_KEY = os.environ["SCRAPER_API_KEY"]
    TIMEOUT_MINUTES = 10

    def __init__(self, mode: Literal["batch", "async"] = "batch"):
        self.scraper_config = self.get_scraper_config()
        self.mode = mode

    @abstractmethod
    def get_scraper_config(self) -> Dict:
        """Return scraper configuration for the specific store"""
        pass

    def _extract_next_data(self, html: str) -> Optional[Dict]:
        """Extract __NEXT_DATA__ from HTML"""
        try:
            from parsel import Selector
            selector = Selector(text=html)
            scripts = selector.css("script#__NEXT_DATA__::text").get()
            return json.loads(scripts) if scripts else None
        except Exception as e:
            logger.error(f"Error extracting __NEXT_DATA__: {str(e)}")
            return None

    def _extract_price_with_regex(self, text: str) -> Optional[float]:
        """Extract price from text using regex"""
        import re
        match = re.search(r'\$?(\d+\.?\d*)', text)
        return float(match.group(1)) if match else None

    @abstractmethod
    async def extract_product_info(self, html: str, url: str) -> Dict:
        """Extract all product information from HTML content"""
        pass

    async def get_raw_content(self, urls: List[str]) -> Dict[str, Dict]:
        """Get raw HTML/JSON content for URLs without processing"""
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
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        }
                    else:
                        return {
                            "error": "No HTML content in response",
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        }

                await asyncio.sleep(5)

        except Exception as e:
            return {
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

    async def _get_raw_batch(self, urls: List[str], client: httpx.AsyncClient) -> Dict[str, Dict]:
        """Get raw content for multiple URLs using batch processing"""
        try:
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
            "category": str(product_info.get("category")) if product_info.get("category") else None
        }

        return standardized

    async def get_prices(self, urls: List[str]) -> Dict[str, Dict]:
        """Get product information for multiple URLs"""
        raw_results = await self.get_raw_content(urls)
        processed_results = {}
        
        for url, result in raw_results.items():
            if "content" in result:
                try:
                    product_info = await self.extract_product_info(result["content"], url)
                    processed_results[url] = self.standardize_output(product_info) if product_info else None
                except Exception as e:
                    logger.error(f"Error processing URL {url}: {str(e)}")
                    processed_results[url] = None
            else:
                processed_results[url] = None

        return processed_results
