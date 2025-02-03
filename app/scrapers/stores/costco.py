from typing import Dict, Optional
from ..base import BaseScraper
import json
from parsel import Selector
import logging

logger = logging.getLogger(__name__)

class CostcoScraper(BaseScraper):
    """Scraper for Costco products."""
    
    store_name = "costco"
    url_pattern = r"(?:www\.)?costco\.com"
    
    def get_scraper_config(self) -> dict:
        """Get Costco-specific scraper configuration."""
        return {
            "premium": "true",
            "country": "us",
            "render": "true",
            "keep_headers": "true",
            "headers": {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5"
            }
        }

    async def extract_product_info(self, html: str, url: str) -> Optional[Dict]:
        """Extract product information from Costco HTML."""
        try:
            selector = Selector(text=html)
            
            # Extract product data from script tag
            script = selector.css('script#productDataJson::text').get()
            if not script:
                logger.error("Could not find product JSON data")
                return None
                
            data = json.loads(script)
            if not isinstance(data, dict):
                logger.error("Invalid product data format")
                return None

            # Extract basic info
            name = data.get("name")
            if not name:
                logger.error("No product name found")
                return None

            # Extract price info
            price_info = data.get("productPricing", {})
            price = price_info.get("finalPrice")
            price_string = price_info.get("formattedFinalPrice")

            # Extract price per unit info
            unit_price_info = price_info.get("unitPrice", {})
            price_per_unit = unit_price_info.get("value")
            price_per_unit_string = unit_price_info.get("formattedValue")

            # Extract additional info
            brand = data.get("brandName")
            sku = data.get("itemNumber")
            category = data.get("categoryString")

            # Extract store info
            store_info = data.get("warehouseInfo", {})
            store_id = store_info.get("warehouseId")
            store_address = store_info.get("address", {}).get("address1")
            store_zip = store_info.get("address", {}).get("zipCode")

            return {
                "store": self.store_name,
                "url": url,
                "name": name,
                "price": float(price) if price else None,
                "price_string": price_string,
                "price_per_unit": float(price_per_unit) if price_per_unit else None,
                "price_per_unit_string": price_per_unit_string,
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