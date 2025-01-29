import json
from parsel import Selector
from .base_scraper import BaseScraper, logger
from typing import Dict, Optional, Any
from datetime import datetime, timezone
import traceback

class WalmartScraper(BaseScraper):
    """Scraper implementation for Walmart."""

    def get_scraper_config(self) -> Dict[str, Any]:
        """Return scraper configuration for Walmart."""
        return {
            "premium": False,
            "country_code": "us",
            "device_type": "desktop",
            "keep_headers": True,
            "headers": {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
        }

    async def extract_product_info(self, html: str, url: str) -> Optional[Dict[str, Any]]:
        """
        Extract product information from Walmart HTML content.
        
        Args:
            html: The HTML content to extract information from.
            url: The URL the content was fetched from.
            
        Returns:
            A dictionary containing product information, or None if extraction failed.
        """
        try:
            logger.info(f"Starting to extract product info for URL: {url}")
            selector = Selector(text=html)
            scripts = selector.css("script#__NEXT_DATA__::text").get()
            if not scripts:
                logger.error("Could not find __NEXT_DATA__ script in HTML")
                return None
            
            logger.info("Found __NEXT_DATA__ script, parsing JSON")
            try:
                data = json.loads(scripts)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON data: {e}")
                return None

            product = (
                data.get("props", {})
                    .get("pageProps", {})
                    .get("initialData", {})
                    .get("data", {})
                    .get("product", {})
            )

            if not product:
                logger.error("No product data found in JSON")
                return None

            # Extract price information
            price_info = product.get("priceInfo", {}).get("unitPrice", {})
            price = price_info.get("price")
            price_string = price_info.get("priceString")
            name = product.get("name")

            if not name:
                logger.error("No product name found")
                return None

            # Extract additional information
            store_info = (
                data.get("props", {})
                    .get("pageProps", {})
                    .get("initialData", {})
                    .get("data", {})
                    .get("store", {})
            )

            store_id = store_info.get("id")
            store_address = store_info.get("address", {}).get("streetAddress")
            store_zip = store_info.get("address", {}).get("postalCode")

            # Extract brand and category
            brand = product.get("brand")
            category = None
            breadcrumbs = product.get("breadcrumb", [])
            if breadcrumbs:
                category = " > ".join(crumb.get("name", "") for crumb in breadcrumbs)

            # Extract SKU/item ID
            sku = product.get("usItemId") or product.get("productId")

            # Extract price per unit
            price_per_unit_info = product.get("priceInfo", {}).get("unitPriceDisplayValue", {})
            price_per_unit = None
            price_per_unit_string = None
            if price_per_unit_info:
                try:
                    # Try to extract numeric value from string like "$1.99/oz"
                    import re
                    match = re.search(r'\$(\d+\.?\d*)/(\w+)', price_per_unit_info)
                    if match:
                        price_per_unit = float(match.group(1))
                        price_per_unit_string = price_per_unit_info
                except (ValueError, AttributeError) as e:
                    logger.warning(f"Failed to parse price per unit: {e}")

            result = {
                "store": "walmart",
                "url": url,
                "name": name,
                "price": float(price) if price else None,
                "price_string": price_string,
                "price_per_unit": price_per_unit,
                "price_per_unit_string": price_per_unit_string,
                "store_id": store_id,
                "store_address": store_address,
                "store_zip": store_zip,
                "brand": brand,
                "sku": sku,
                "category": category,
                "timestamp": datetime.now(timezone.utc)
            }
            
            logger.info(f"Successfully extracted product info: {result}")
            return result

        except Exception as e:
            logger.error(f"Error parsing Walmart product info: {e}")
            logger.error(traceback.format_exc())
            return None

    # Remove this method as it's not needed and could cause confusion
    # async def extract_price(self, html: str) -> float:
    #     product_info = await self.extract_product_info(html, "")
    #     return product_info.get("price") if product_info else None 