from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Literal
import logging
import httpx
import time
import os
import asyncio
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BaseScraper(ABC):
    API_KEY = os.environ["SCRAPER_API_KEY"]
    TIMEOUT_MINUTES = 1  # Reduced timeout

    def __init__(self, mode: Literal["batch", "async"] = "async"):
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
                return {"error": f"API request failed with status {response.status_code}"}

            job_data = response.json()
            job_id = job_data.get('id')
            status_url = job_data.get('statusUrl')

            if not job_id:
                return {"error": "No job ID received"}

            start_time = time.time()
            while True:
                if (time.time() - start_time) / 60 >= self.TIMEOUT_MINUTES:
                    return {"error": "Job timed out"}

                status_response = await client.get(status_url)
                status_data = status_response.json()
                status = status_data.get('status')

                if status == 'failed':
                    return {"error": "Job failed"}
                elif status == 'finished':
                    html = status_data.get('response', {}).get('body')
                    return {"content": html} if html else {"error": "No HTML content"}

                await asyncio.sleep(10)  # Increased sleep time

        except Exception as e:
            return {"error": str(e)}

    async def get_prices(self, urls: List[str]) -> Dict[str, Dict]:
        """Get product information for multiple URLs"""
        url_strings = [str(url) for url in urls]
        results = {}

        async with httpx.AsyncClient(verify=False) as client:
            tasks = [self._get_raw_single(url, client) for url in url_strings]
            raw_results = await asyncio.gather(*tasks)
            results = dict(zip(url_strings, raw_results))

        processed_results = {}
        for url, result in results.items():
            if "content" in result:
                try:
                    product_info = await self.extract_product_info(result["content"], url)
                    processed_results[url] = product_info
                except Exception as e:
                    logger.error(f"Error processing URL {url}: {str(e)}")
                    processed_results[url] = None
            else:
                processed_results[url] = None

        return processed_results