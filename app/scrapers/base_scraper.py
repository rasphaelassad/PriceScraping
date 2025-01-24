from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Literal
import logging
import httpx
import time
import os
import asyncio
from dotenv import load_dotenv
from datetime import datetime

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

    def standardize_output(self, product_info: Dict) -> Dict:
        """Standardize the output format across all scrapers"""
        if not product_info:
            return None

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
            "category": str(product_info.get("category")) if product_info.get("category") else None
        }

        return standardized

    async def _process_single_async_job(self, url: str, client: httpx.AsyncClient) -> Optional[Dict]:
        """Process a single URL using async ScraperAPI endpoint"""
        try:
            # Submit single job
            api_url = "https://async.scraperapi.com/jobs"
            payload = {
                "url": url,
                "apiKey": self.API_KEY,
                **self.scraper_config
            }

            response = await client.post(api_url, json=payload)
            if response.status_code != 200:
                logger.error(f"API request failed for URL {url} with status {response.status_code}")
                return None

            job_data = response.json()
            job_id = job_data.get('id')
            status_url = job_data.get('statusUrl')

            if not job_id:
                logger.error(f"No job ID received for URL {url}")
                return None

            # Poll for job completion
            start_time = time.time()
            while True:
                # Check timeout
                if (time.time() - start_time) / 60 >= self.TIMEOUT_MINUTES:
                    logger.warning(f"Job timed out for URL {url}")
                    return None

                status_response = await client.get(status_url)
                status_data = status_response.json()
                status = status_data.get('status')

                if status == 'failed':
                    logger.error(f"Job failed for URL {url}")
                    return None
                elif status == 'finished':
                    html = status_data.get('response', {}).get('body')
                    if html:
                        try:
                            product_info = await self.extract_product_info(html, url)
                            return self.standardize_output(product_info) if product_info else None
                        except Exception as e:
                            logger.error(f"Error processing URL {url}: {str(e)}")
                            return None
                    else:
                        logger.error(f"No HTML content in response for URL {url}")
                        return None

                await asyncio.sleep(5)  # Wait before next poll

        except Exception as e:
            logger.error(f"Error processing URL {url}: {str(e)}")
            return None

    async def _process_batch_jobs(self, urls: List[str], client: httpx.AsyncClient) -> Dict[str, Dict]:
        """Process multiple URLs using batch ScraperAPI endpoint"""
        try:
            # Submit batch job
            api_url = "https://async.scraperapi.com/batchjobs"
            payload = {
                "urls": [str(url) for url in urls],
                "apiKey": self.API_KEY,
                "apiParams": self.scraper_config
            }

            logger.info(f"Sending batch request to {api_url}")
            response = await client.post(api_url, json=payload)
            
            if response.status_code != 200:
                logger.error(f"Batch API request failed with status {response.status_code}")
                return {url: None for url in urls}
            
            jobs = response.json()
            job_statuses = {job['id']: {'status': 'running', 'url': job['url'], 'statusUrl': job['statusUrl']} for job in jobs}
            results = {}
            start_time = time.time()

            # Poll for all jobs completion
            while any(status['status'] == 'running' for status in job_statuses.values()):
                if (time.time() - start_time) / 60 >= self.TIMEOUT_MINUTES:
                    logger.warning(f"Batch scraping timed out after {self.TIMEOUT_MINUTES} minutes")
                    for job_info in job_statuses.values():
                        if job_info['status'] == 'running':
                            job_info['status'] = 'failed'
                            results[job_info['url']] = None
                    break

                for job_id, job_info in job_statuses.items():
                    if job_info['status'] == 'running':
                        status_response = await client.get(job_info['statusUrl'])
                        status_data = status_response.json()
                        current_status = status_data.get('status')
                        
                        if current_status == 'failed':
                            job_info['status'] = 'failed'
                            results[job_info['url']] = None
                        elif current_status == 'finished':
                            job_info['status'] = 'finished'
                            html = status_data.get('response', {}).get('body')
                            if html:
                                try:
                                    product_info = await self.extract_product_info(html, job_info['url'])
                                    results[job_info['url']] = self.standardize_output(product_info) if product_info else None
                                except Exception as e:
                                    logger.error(f"Error processing URL {job_info['url']}: {str(e)}")
                                    results[job_info['url']] = None
                            else:
                                results[job_info['url']] = None

                await asyncio.sleep(5)

            # Fill in any missing results
            for url in urls:
                if url not in results:
                    results[url] = None

            return results

        except Exception as e:
            logger.error(f"Error in batch processing: {str(e)}")
            return {url: None for url in urls}

    async def get_prices(self, urls: List[str]) -> Dict[str, Dict]:
        """Get product information for multiple URLs"""
        # Convert HttpUrl objects to strings if needed
        url_strings = [str(url) for url in urls]
        
        async with httpx.AsyncClient(verify=False) as client:
            if self.mode == "batch":
                return await self._process_batch_jobs(url_strings, client)
            else:  # async mode
                # Process all URLs in parallel
                tasks = [self._process_single_async_job(url, client) for url in url_strings]
                results = await asyncio.gather(*tasks)
                return dict(zip(url_strings, results))