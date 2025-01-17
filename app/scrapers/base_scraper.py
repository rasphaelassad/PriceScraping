from abc import ABC, abstractmethod
from typing import Dict, List
import logging
import httpx
import time
import os
import asyncio

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BaseScraper(ABC):
    API_KEY = os.environ["SCRAPER_API_KEY"]
    print(API_KEY)

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
        
        # Convert HttpUrl objects to strings
        url_strings = [str(url) for url in urls]
        
        async with httpx.AsyncClient(verify=False) as client:
            try:
                # Submit batch job
                api_url = "https://async.scraperapi.com/batchjobs"
                payload = {
                    "urls": url_strings,  # Use the string versions
                    "apiKey": self.API_KEY,
                    "apiParams": self.scraper_config
                }

                # Debug logging
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

        return results