from typing import Dict, List, Optional, Any
import json
import logging
import traceback
from datetime import datetime, timezone
from .base_scraper import BaseScraper
import asyncio
from fastapi import HTTPException
import aiohttp
from app.core.config import get_settings
import uuid
from bs4 import BeautifulSoup
import re
import httpx

logger = logging.getLogger(__name__)

class AlbertsonsScraper(BaseScraper):
    """Scraper implementation for Albertsons."""

    def __init__(self, mode: str = "batch"):
        """Initialize the scraper in async mode."""
        super().__init__(mode)
        self.store_name = "albertsons"
    
    def get_scraper_config(self) -> Dict:
        """Return scraper configuration for Albertsons."""
        return {
            "country": "us",
            "headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "ocp-apim-subscription-key": "6c21edb7bcda4f0e918348db16147431"
            }
        }

    def transform_url(self, url: str) -> str:
        """Transform product detail URL to API URL for scraping."""
        try:
            if "product-details." in url:
                # Extract product ID from URL
                product_id = url.split("product-details.")[-1].split(".")[0]
                # Transform to API URL format
                return f"https://www.albertsons.com/abs/pub/xapi/product/v2/pdpdata?bpn={product_id}&banner=albertsons&storeId=177"
            return url
        except Exception as e:
            logger.error(f"Error transforming URL {url}: {str(e)}")
            return url

    async def extract_product_info(self, html: str, url: str) -> Optional[Dict]:
        """Extract product information from Albertsons API response."""
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Find product data in script tag
            script_tag = soup.find('script', {'type': 'application/ld+json'})
            if not script_tag:
                return None
                
            product_data = json.loads(script_tag.string)
            
            # Extract price
            price_elem = soup.find('span', {'class': 'product-price'})
            price_string = price_elem.text.strip() if price_elem else None
            price = float(re.sub(r'[^\d.]', '', price_string)) if price_string else None
            
            # Extract other information
            name = product_data.get('name')
            brand = product_data.get('brand', {}).get('name')
            sku = product_data.get('sku')
            
            return {
                "store": "albertsons",
                "url": url,
                "name": name,
                "price": price,
                "price_string": price_string,
                "brand": brand,
                "sku": sku
            }
            
        except Exception as e:
            self.logger.error(f"Error extracting product info: {str(e)}")
            return None

    async def get_price(self, url: str) -> Dict:
        """Get price for a single URL"""
        try:
            # Transform the URL before fetching
            api_url = self.transform_url(url)
            
            async with httpx.AsyncClient(verify=False) as client:
                result = await self._get_raw_single(api_url, client)
                
                if "error" in result:
                    raise ValueError(result["error"])
                
                # For API URLs, we need to parse JSON instead of HTML
                if "xapi" in api_url:
                    try:
                        product_data = json.loads(result["content"])
                        product_info = {
                            "store": "albertsons",
                            "url": url,  # Keep original URL for reference
                            "name": product_data.get("name"),
                            "price": float(product_data.get("price", {}).get("regular", 0)),
                            "price_string": f"${product_data.get('price', {}).get('regular', 0)}",
                            "brand": product_data.get("brand"),
                            "sku": product_data.get("sku"),
                            "store_id": product_data.get("storeId")
                        }
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse API response: {e}")
                        raise ValueError("Failed to parse API response")
                else:
                    # Fallback to HTML parsing if not an API URL
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
            logger.error(f"Error getting price for {url}: {str(e)}")
            return {
                "request_status": {
                    "status": "failed",
                    "error_message": str(e),
                    "start_time": datetime.now(timezone.utc),
                    "elapsed_time_seconds": 0.0,
                    "job_id": str(uuid.uuid4())
                }
            }