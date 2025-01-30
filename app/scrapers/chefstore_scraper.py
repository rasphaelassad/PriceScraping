from typing import Dict, Optional, Any
import json
import logging
from datetime import datetime, timezone
from .base_scraper import BaseScraper
import httpx
from bs4 import BeautifulSoup
import re
import uuid

logger = logging.getLogger(__name__)

class ChefStoreScraper(BaseScraper):
    """Scraper implementation for ChefStore."""

    def __init__(self, mode: str = "batch"):
        super().__init__(mode)
        self.store_name = "chefstore"

    def get_scraper_config(self) -> Dict:
        return {
            "country": "us",
            "render": "true",  # ChefStore requires JavaScript rendering
            "headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
        }

    async def extract_product_info(self, html: str, url: str) -> Optional[Dict]:
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Extract product name
            name_elem = soup.find('h1', {'class': 'product-name'})
            name = name_elem.text.strip() if name_elem else None
            
            # Extract price
            price_elem = soup.find('span', {'class': 'price-value'})
            price_string = price_elem.text.strip() if price_elem else None
            price = float(re.sub(r'[^\d.]', '', price_string)) if price_string else None
            
            # Extract other information
            sku_elem = soup.find('span', {'class': 'product-id'})
            sku = sku_elem.text.strip() if sku_elem else None
            
            return {
                "store": "chefstore",
                "url": url,
                "name": name,
                "price": price,
                "price_string": price_string,
                "sku": sku
            }
            
        except Exception as e:
            logger.error(f"Error extracting ChefStore product info: {str(e)}")
            return None

    async def get_price(self, url: str) -> Dict:
        try:
            async with httpx.AsyncClient(verify=False) as client:
                result = await self._get_raw_single(url, client)
                
                if "error" in result:
                    raise ValueError(result["error"])
                
                product_info = await self.extract_product_info(result["content"], url)
            
            if not product_info:
                raise ValueError("Failed to extract product information")
                
            return {
                "product_info": self.standardize_output(product_info),
                "request_status": {
                    "status": "success",
                    "start_time": result["start_time"],
                    "elapsed_time_seconds": 0.0,
                    "job_id": str(uuid.uuid4())
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting ChefStore price for {url}: {str(e)}")
            return {
                "request_status": {
                    "status": "failed",
                    "error_message": str(e),
                    "start_time": datetime.now(timezone.utc),
                    "elapsed_time_seconds": 0.0,
                    "job_id": str(uuid.uuid4())
                }
            }
