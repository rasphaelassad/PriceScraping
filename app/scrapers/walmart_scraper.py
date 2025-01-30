import json
from parsel import Selector
from .base_scraper import BaseScraper, logger
from typing import Dict, Optional

class WalmartScraper(BaseScraper):
    def get_scraper_config(self) -> dict:
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
        try:
            logger.info(f"Starting to extract product info for URL: {url}")
            selector = Selector(text=html)
            scripts = selector.css("script#__NEXT_DATA__::text").get()
            if not scripts:
                logger.error("Could not find __NEXT_DATA__ script in HTML")
                return None
            
            logger.info("Found __NEXT_DATA__ script, parsing JSON")
            data = json.loads(scripts)

            product = (
                data.get("props", {})
                    .get("pageProps", {})
                    .get("initialData", {})
                    .get("data", {})
                    .get("product", {})
            )

            # Extract basic product info
            price_info = product.get("priceInfo", {}).get("unitPrice", {})
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

            result = {
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
            
            logger.info(f"Successfully extracted product info: {result}")
            return result
        except Exception as e:
            logger.error(f"Error parsing Walmart product info: {str(e)}")
            return None