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
            "headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Accept": "application/json",
                "Accept-Language": "en-US,en;q=0.9",
                "ocp-apim-subscription-key": "6c21edb7bcda4f0e918348db16147431"
            },
            "country": "us",
            "keepHeaders": True
        }


    def transform_url(self, url: str) -> str:
        """Transform Albertsons product URL to API URL."""
        try:
            # Extract product ID from URL
            match = re.search(r'product-details\.(\d+)\.html', url)
            if not match:
                logger.error(f"Could not extract product ID from URL: {url}")
                return url
                
            product_id = match.group(1)
            store_id = "177"  # Default store ID for now
            api_url = f"https://www.albertsons.com/abs/pub/xapi/pgm/v1/product/{product_id}/channel/instore/store/{store_id}"
            logger.info(f"Transformed URL {url} to {api_url}")
            return api_url
            
        except Exception as e:
            logger.error(f"Error transforming URL {url}: {str(e)}")
            return url

    async def extract_product_info(self, html: str, url: str) -> Optional[Dict]:
        """Extract product information from API response."""
        try:
            # Parse JSON response
            data = json.loads(html)
            
            if not data:
                logger.error("Empty response from API")
                return None
            
            # Extract store info from URL
            store_match = re.search(r'/store/(\d+)/', url)
            store_id = store_match.group(1) if store_match else None
            
            # Extract price info
            price = None
            price_string = None
            price_per_unit = None
            price_per_unit_string = None
            
            if "items" in data and len(data["items"]) > 0:
                item = data["items"][0]
                
                # Regular price
                if "price" in item:
                    try:
                        price = float(item["price"]["regular"])
                        price_string = f"${price:.2f}"
                    except (KeyError, ValueError) as e:
                        logger.warning(f"Error extracting regular price: {e}")
                
                # Price per unit
                if "pricePer" in item:
                    try:
                        price_per_unit = float(item["pricePer"]["price"])
                        unit = item["pricePer"]["unit"]
                        price_per_unit_string = f"${price_per_unit:.2f}/{unit}"
                    except (KeyError, ValueError) as e:
                        logger.warning(f"Error extracting price per unit: {e}")
                
                # Get original URL from the transformed URL if needed
                original_url = url
                if '/xapi/pgm/v1/product/' in url:
                    product_id = re.search(r'/product/(\d+)/', url)
                    if product_id:
                        original_url = f"https://www.albertsons.com/shop/product-details.{product_id.group(1)}.html"
                
                # Build product info
                return {
                    "store": "albertsons",
                    "url": original_url,  # Always use the original product URL
                    "name": item.get("name", ""),
                    "price": price,
                    "price_string": price_string,
                    "price_per_unit": price_per_unit,
                    "price_per_unit_string": price_per_unit_string,
                    "store_id": store_id,
                    "store_address": None,  # Not available in API response
                    "store_zip": None,  # Not available in API response
                    "brand": item.get("brand", {}).get("name", None),
                    "sku": item.get("upc", None),
                    "category": item.get("categories", [None])[0]
                }
            
            logger.error("No items found in API response")
            return None
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Error extracting product info: {str(e)}")
            return None