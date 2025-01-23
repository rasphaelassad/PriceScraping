from abc import ABC, abstractmethod
from typing import Dict, List, Optional
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
    
    def __init__(self):
        self.scraper_config = self.get_scraper_config()

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

    async def get_prices(self, urls: List[str]) -> Dict[str, Dict]:
        """Get product information for multiple URLs in a single batch request"""
        results = {}
        start_time = time.time()
        
        # Convert HttpUrl objects to strings
        url_strings = [str(url) for url in urls]
        
        async with httpx.AsyncClient(verify=False) as client:
            try:
                # Submit batch job
                api_url = "https://async.scraperapi.com/batchjobs"
                payload = {
                    "urls": url_strings,
                    "apiKey": self.API_KEY,
                    "apiParams": self.scraper_config
                }

                logger.info(f"Sending request to {api_url}")
                logger.info(f"Payload: {payload}")

                try:
                    response = await client.post(api_url, json=payload)
                    logger.info(f"Response status: {response.status_code}")
                    
                    if response.status_code != 200:
                        logger.error(f"API request failed with status {response.status_code}")
                        logger.error(f"Response body: {response.text}")
                        return {url: None for url in urls}
                    
                    jobs = response.json()
                    
                    # Track all jobs
                    job_statuses = {job['id']: {'status': 'running', 'url': job['url'], 'statusUrl': job['statusUrl']} for job in jobs}

                    # Poll for all jobs completion
                    while any(status['status'] == 'running' for status in job_statuses.values()):
                        # Check if we've exceeded the timeout
                        elapsed_minutes = (time.time() - start_time) / 60
                        if elapsed_minutes >= self.TIMEOUT_MINUTES:
                            logger.warning(f"Scraping timed out after {self.TIMEOUT_MINUTES} minutes")
                            # Mark any remaining running jobs as failed
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
                                logger.info(f"Job {job_id} for URL {job_info['url']} status: {current_status}")
                                
                                if current_status == 'failed':
                                    logger.info(f"Setting job {job_id} to failed")
                                    job_info['status'] = 'failed'
                                    results[job_info['url']] = None
                                elif current_status == 'finished':
                                    logger.info(f"Setting job {job_id} to finished")
                                    job_info['status'] = 'finished'
                                    # Extract HTML from the response body
                                    html = status_data.get('response', {}).get('body')
                                    if html:
                                        try:
                                            product_info = await self.extract_product_info(html, job_info['url'])
                                            if product_info:
                                                product_info = self.standardize_output(product_info)
                                            results[job_info['url']] = product_info
                                        except Exception as e:
                                            logger.error(f"Error processing URL {job_info['url']}: {str(e)}")
                                            results[job_info['url']] = None
                                    else:
                                        logger.error(f"No HTML content in response for job {job_id}")
                                        results[job_info['url']] = None

                        await asyncio.sleep(5)  # Wait before next poll

                    # Fill in any missing results
                    for url in urls:
                        if str(url) not in results:
                            results[str(url)] = None

                except httpx.RequestError as e:
                    logger.error(f"Network error occurred: {str(e)}")
                    return {str(url): None for url in urls}
                except Exception as e:
                    logger.error(f"Unexpected error during API call: {str(e)}")
                    return {str(url): None for url in urls}

            except Exception as e:
                logger.error(f"Error in batch processing: {str(e)}")
                results = {str(url): None for url in urls}

        logger.info(f"Final results before return: {results}")
        return results