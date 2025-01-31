
from parsel import Selector
from .base_scraper import BaseScraper, logger
from typing import Dict, Optional
import json

class ChefStoreScraper(BaseScraper):
    def get_scraper_config(self) -> dict:
        return {
            'max_cost': '30',
            "retry_times": 3,
            "premium": False,
            "country_code": "us",
            "device_type": "desktop",
            "keep_headers": True,
            "headers": {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5"
            }
        }

    def _extract_json_ld(self, html: str) -> Optional[Dict]:
        """Extract JSON-LD data from HTML"""
        try:
            selector = Selector(text=html)
            scripts = selector.css('script[type="application/ld+json"]::text').get()
            return json.loads(scripts) if scripts else None
        except Exception as e:
            logger.error(f"Error extracting JSON-LD: {str(e)}")
            return None

    async def extract_product_info(self, html: str, url: str) -> Dict:
        try:
            logger.info(f"Starting to extract product info for URL: {url}")
            selector = Selector(text=html)
            
            data = self._extract_json_ld(html)
            if not data:
                logger.error("Could not find JSON-LD script in HTML")
                return None
            
            store_link = selector.css('a.store-address-link::attr(href)').get()
            store_id = store_link.split('/')[-2] if store_link else None
            store_address = selector.css('a.store-address-link::text').get()
            
            price = None
            if "offers" in data:
                if isinstance(data["offers"], dict):
                    if "highPrice" in data["offers"]:
                        price = data["offers"]["highPrice"]
                    elif "price" in data["offers"]:
                        price = data["offers"]["price"]
            
            result = {
                "store": "chefstore",
                "url": url,
                "name": data.get("name"),
                "price": float(price) if price else None,
                "price_string": f"${price}" if price else None,
                "store_id": store_id,
                "store_address": store_address,
                "sku": data.get("sku"),
                "brand": data.get("brand", {}).get("name"),
                "category": data.get("category")
            }
            
            logger.info(f"Successfully extracted product info: {result}")
            return result
            
        except Exception as e:
            logger.error(f"Error parsing ChefStore product info: {str(e)}")
            return None
