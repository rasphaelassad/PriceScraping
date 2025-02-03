from typing import Dict, Optional
from ..base import BaseScraper
import json
from parsel import Selector
import logging

logger = logging.getLogger(__name__)

class WalmartScraper(BaseScraper):
    """Scraper for Walmart products."""
    
    store_name = "walmart"
    url_pattern = r"(?:www\.)?walmart\.com"
    
    def get_scraper_config(self) -> dict:
        """Get Walmart-specific scraper configuration."""
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

            # Extract price per unit info
            unit_price_info = product.get("priceInfo", {}).get("unitPrice", {})
            price_per_unit = unit_price_info.get("price")
            price_per_unit_string = unit_price_info.get("priceString")

            # Extract additional product info
            sku = product.get("usItemId")
            brand = product.get("brand")
            category = product.get("category")
            store_info = product.get("store", {})
            store_id = store_info.get("id")
            store_address = store_info.get("address", {}).get("address")
            store_zip = store_info.get("address", {}).get("postalCode")

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