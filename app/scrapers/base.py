"""Base scraper implementation."""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import logging
import aiohttp
from datetime import datetime, timezone
from app.core.config import get_settings
import re
import uuid
import asyncio
import json

logger = logging.getLogger(__name__)

class BaseScraper(ABC):
    """Base class for all store-specific scrapers."""
    
    # Store name and URL pattern - must be set in subclasses
    store_name: str = ""
    url_pattern: str = ""
    
    def __init__(self):
        """Initialize the scraper with API key and common settings."""
        if not self.store_name:
            raise ValueError("Scraper must define store_name")
            
        self.settings = get_settings()
        self.api_key = self.settings.scraper_api_key
        if not self.api_key:
            raise ValueError("SCRAPER_API_KEY environment variable not set")
            
        # Set up API endpoint
        self.base_url = self.settings.scraper_api_base_url

    @abstractmethod
    def get_scraper_config(self) -> dict:
        """Get store-specific scraper configuration."""
        pass

    async def get_raw_content(self, url: str) -> Dict[str, Any]:
        """Get raw HTML content for a single URL without extracting product info."""
        original_url = url
        api_url = self.transform_url(url)
        
        try:
            raw_result = await self._fetch_data_async_from_scraperapi(api_url)
            if "error" in raw_result:
                logger.error(f"Error fetching URL {url}: {raw_result['error']}")
                raise ValueError(raw_result["error"])
                
            return {
                "url": original_url,
                "content": raw_result["content"],
                "job_id": raw_result.get("job_id"),
                "started_at": raw_result.get("started_at"),
                "completed_at": raw_result.get("completed_at")
            }
        except Exception as e:
            logger.error(f"Error getting raw content for URL {url}: {e}")
            raise

    async def fetch_data_async_from_scraperapi(self, url: str) -> Dict[str, Any]:
        """Fetch URL content with ScraperAPI using scraper configuration."""
        config = self.get_scraper_config()
        try:
            async with aiohttp.ClientSession() as session:
                # Submit job to ScraperAPI
                payload = {
                    'apiKey': self.api_key,
                    'url': url,
                    **config #In the future this may need to be nested under apiParams as per the docs
                }
                
                logger.debug(f"Sending payload to ScraperAPI: {payload}")
                logger.info(f"Fetching URL with ScraperAPI: {url}")
                
                # Submit the job
                async with session.post(self.base_url, json=payload) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"ScraperAPI error: {error_text}")
                        return {"error": f"ScraperAPI error: {error_text}"}
                    
                    job_data = await response.json()
                    logger.debug(f"Initial job response: {job_data}")
                    
                    job_id = job_data.get('id')
                    started_at = datetime.now(timezone.utc)
                    status_url = job_data.get('statusUrl')
                    logger.info(f"Status URL: {status_url}")

                    if not job_id or not status_url:
                        return {"error": "No job ID or status URL received from ScraperAPI"}

                    # Track the last seen attempt number to detect changes
                    last_attempt = 0
                    max_attempts = 4  # Give up after 4 attempts

                    while True:  # We'll control the loop with our own conditions
                        async with session.get(status_url) as status_response:
                            if status_response.status != 200:
                                error_text = await status_response.text()
                                return {"error": f"Status check failed: {error_text}"}

                            try:
                                status_data = json.loads(await status_response.text())
                                logger.debug(f"Status data received: {status_data}")
                                
                                status = status_data.get('status')
                                current_attempt = status_data.get('attempts', 0)
                                supposed_to_run_at = status_data.get('supposedToRunAt')

                                if status == 'finished':
                                    response_data = status_data.get('response', {})
                                    if not response_data:
                                        return {"error": "No response data in finished job"}
                                        
                                    body = response_data.get('body')
                                    if not body:
                                        return {"error": "No body content in response"}
                                    
                                    return {
                                        "job_id": job_id,
                                        "started_at": started_at,
                                        "completed_at": datetime.now(timezone.utc),
                                        "content": body
                                    }
                                elif status == 'failed':
                                    return {"error": f"ScraperAPI job failed: {status_data.get('error')}"}

                                elif status == 'running':
                                    if current_attempt >= max_attempts:
                                        return {"error": f"Job timed out after {max_attempts} attempts"}
                                    
                                    # If this is a new attempt, log it
                                    if current_attempt > last_attempt:
                                        logger.info(f"Attempt {current_attempt} of {max_attempts}")
                                        last_attempt = current_attempt

                                    if supposed_to_run_at:
                                        # Convert supposedToRunAt to datetime
                                        try:
                                            run_time = datetime.fromisoformat(supposed_to_run_at.replace('Z', '+00:00'))
                                            now = datetime.now(timezone.utc)
                                            
                                            # If it's not time to run yet, wait until then plus 10 seconds
                                            if run_time > now:
                                                wait_seconds = (run_time - now).total_seconds() + 10
                                                logger.info(f"Waiting {wait_seconds:.1f} seconds until next scheduled run time")
                                                await asyncio.sleep(wait_seconds)
                                            else:
                                                # If we're past the scheduled time, wait 10 seconds before checking again
                                                await asyncio.sleep(10)
                                        except ValueError as e:
                                            logger.error(f"Error parsing supposedToRunAt time: {e}")
                                            await asyncio.sleep(10)
                                    else:
                                        # If no supposedToRunAt time, wait 10 seconds
                                        await asyncio.sleep(10)
                                else:
                                    return {"error": f"Unknown job status: {status}"}
                            except json.JSONDecodeError as e:
                                logger.error(f"Failed to parse JSON response: {e}")
                                return {"error": f"Invalid JSON response: {str(e)}"}
                            except Exception as e:
                                logger.error(f"Error parsing status response: {str(e)}")
                                return {"error": f"Error parsing status response: {str(e)}"}

        except Exception as e:
            logger.error(f"Error fetching URL {url}: {str(e)}")
            return {"error": f"Error fetching URL: {str(e)}"}

    @abstractmethod
    async def extract_product_info(self, html: str, url: str) -> Optional[Dict]:
        """Extract product information from HTML content."""
        pass 