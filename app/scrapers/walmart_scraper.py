from typing import Dict, Optional
from .base_scraper import BaseScraper
import json
from parsel import Selector
import logging

logger = logging.getLogger(__name__)

class WalmartScraper(BaseScraper):
    def get_scraper_config(self) -> dict:
        """Get Walmart-specific scraper configuration."""
        return {
            "premium": False,
            "country_code": "us",
            "device_type": "desktop",
            "keep_headers": True,
            "headers": {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5"
            }
        }

    async def extract_product_info(self, html: str, url: str) -> Optional[Dict]:
        """Extract product information from Walmart HTML."""
        try:
            selector = Selector(text=html)
            scripts = selector.css("script#__NEXT_DATA__::text").get()
            if not scripts:
                logger.error("Could not find __NEXT_DATA__ script in HTML")
                return None
            
            data = json.loads(scripts)
            product = (
                data.get("props", {})
                    .get("pageProps", {})
                    .get("initialData", {})
                    .get("data", {})
                    .get("product", {})
            )

            # Extract basic product info
            price_info = product.get("priceInfo", {}).get("currentPrice", {})
            price = price_info.get("price")
            price_string = price_info.get("priceString")
            name = product.get("name")

            # Extract additional product info
            sku = product.get("usItemId")
            brand = product.get("brand")
            category = product.get("category")
            store_info = product.get("store", {})
            store_id = store_info.get("id")
            store_address = store_info.get("address", {}).get("address")
            store_zip = store_info.get("address", {}).get("postalCode")

            return {
                "store": "walmart",
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