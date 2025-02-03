from typing import Dict, Optional
from ..base import BaseScraper
import json
import logging
from parsel import Selector
import re

logger = logging.getLogger(__name__)

class AlbertsonsScraper(BaseScraper):
    """Scraper for Albertsons products."""
    
    store_name = "albertsons"
    url_pattern = r"(?:www\.)?albertsons\.com"
    
    def get_scraper_config(self) -> dict:
        """Get Albertsons-specific scraper configuration."""
        return {
            "country_code": "us",
            "device_type": "desktop",
            "keep_headers": True,
            "headers": {
                "Accept": "application/json",
                "Accept-Language": "en-US,en;q=0.5"
            }
        }

    def transform_url(self, url: str) -> str:
        """Transform Albertsons product URL to API URL."""
        try:
            # Extract product ID from URL
            product_id = re.search(r'product-details\.(\d+)\.html', url)
            if not product_id:
                logger.error(f"Could not extract product ID from URL: {url}")
                return url
                
            # Convert to API URL
            api_url = f"https://www.albertsons.com/abs/pub/xapi/v1/product/{product_id.group(1)}"
            logger.info(f"Transformed URL {url} to {api_url}")
            return api_url
        except Exception as e:
            logger.error(f"Error transforming URL {url}: {e}")
            return url

    async def extract_product_info(self, html: str, url: str) -> Optional[Dict]:
        """Extract product information from Albertsons API response."""
        try:
            data = json.loads(html)
            product = data.get("product", {})
            
            if not product:
                logger.error("No product data found")
                return None

            # Extract basic info
            name = product.get("name")
            if not name:
                logger.error("No product name found")
                return None

            # Extract price info
            price_info = product.get("price", {})
            price = price_info.get("regularPrice")
            price_string = f"${price}" if price else None

            # Extract store info
            store_info = product.get("storeInfo", {})
            store_id = store_info.get("storeId")
            store_address = store_info.get("address", {}).get("line1")
            store_zip = store_info.get("address", {}).get("zipCode")

            # Extract additional info
            brand = product.get("brand")
            sku = product.get("sku")
            category = product.get("category", {}).get("name")

            return {
                "store": self.store_name,
                "url": url,
                "name": name,
                "price": float(price) if price else None,
                "price_string": price_string,
                "store_id": store_id,
                "store_address": store_address,
                "store_zip": store_zip,
                "brand": brand,
                "sku": sku,
                "category": category
            }
        except Exception as e:
            logger.error(f"Error extracting product info: {e}")
            return None