from parsel import Selector
from .base_scraper import BaseScraper, logger
from typing import Dict
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

    async def extract_product_info(self, html: str, url: str) -> Dict:
        try:
            logger.info(f"Starting to extract product info for URL: {url}")
            selector = Selector(text=html)
            
            # Get JSON-LD script content
            scripts = selector.css('script[type="application/ld+json"]::text').get()
            if not scripts:
                logger.error("Could not find JSON-LD script in HTML")
                return None
            
            logger.info("Found JSON-LD script, parsing JSON")
            data = json.loads(scripts)
            
            # Extract store information
            store_link = selector.css('a.store-address-link::attr(href)').get()
            try:
                store_id = store_link.split('/')[-2] if store_link else None
            except (IndexError, AttributeError):
                store_id = None
            store_address = selector.css('a.store-address-link::text').get()
            
            # Extract price from offers
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
