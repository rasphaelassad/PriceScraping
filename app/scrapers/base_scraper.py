from abc import ABC, abstractmethod
from typing import Dict, List
import logging
import aiohttp
import time
import os
import asyncio
import ssl

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BaseScraper(ABC):
    API_KEY = os.environ["SCRAPER_API_KEY"]

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

    async def get_prices(self, urls: List[str]) -> Dict[str, Dict]:
        """Get product information for multiple URLs in a single batch request"""
        results = {}
        
        # Create SSL context that skips verification
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        # Create session with SSL context
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl_context)) as session:
            try:
                # Submit batch job
                api_url = "https://async.scraperapi.com/batchjobs"
                payload = {
                    "urls": urls,
                    "apiKey": self.API_KEY,
                    "apiParams": self.scraper_config
                }

                # Debug logging
                logger.info(f"Sending request to {api_url}")
                logger.info(f"Payload: {payload}")

                try:
                    async with session.post(api_url, json=payload) as response:
                        logger.info(f"Response status: {response.status}")
                        response_text = await response.text()
                        logger.info(f"Response body: {response_text}")
                        
                        if response.status != 200:
                            logger.error(f"API request failed with status {response.status}")
                            logger.error(f"Response body: {response_text}")
                            return {url: None for url in urls}
                        
                        jobs = await response.json()
                        
                        # Track all jobs
                        job_statuses = {job['id']: {'status': 'running', 'url': job['url'], 'statusUrl': job['statusUrl']} for job in jobs}

                        # Poll for all jobs completion
                        while any(status['status'] == 'running' for status in job_statuses.values()):
                            for job_id, job_info in job_statuses.items():
                                if job_info['status'] == 'running':
                                    async with session.get(job_info['statusUrl']) as status_response:
                                        status_data = await status_response.json()
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
                                                    results[job_info['url']] = product_info
                                                except Exception as e:
                                                    logger.error(f"Error processing URL {job_info['url']}: {str(e)}")
                                                    results[job_info['url']] = None
                                            else:
                                                logger.error(f"No HTML content in response for job {job_id}")
                                                results[job_info['url']] = None

                            await asyncio.sleep(5)  # Wait before next poll

                        # No need for separate results fetching anymore
                        # Fill in any missing results
                        for url in urls:
                            if url not in results:
                                results[url] = None

                except aiohttp.ClientError as e:
                    logger.error(f"Network error occurred: {str(e)}")
                    return {url: None for url in urls}
                except Exception as e:
                    logger.error(f"Unexpected error during API call: {str(e)}")
                    return {url: None for url in urls}

            except Exception as e:
                logger.error(f"Error in batch processing: {str(e)}")
                results = {url: None for url in urls}

        return results