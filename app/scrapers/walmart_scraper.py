import json
from parsel import Selector
from .base_scraper import BaseScraper, logger
from typing import Dict

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

    async def extract_product_info(self, html: str, url: str) -> Dict:
        try:
            data = self._extract_next_data(html)
            if not data:
                return None

            product = (
                data.get("props", {})
                    .get("pageProps", {})
                    .get("initialData", {})
                    .get("data", {})
                    .get("product", {})
            )

            price_info = product.get("priceInfo", {}).get("unitPrice", {})

            result = {
                "store": "walmart",
                "url": url,
                "name": product.get("name"),
                "price": float(price_info.get("price")) if price_info.get("price") else None,
                "price_string": price_info.get("priceString")
            }

            return result
        except Exception as e:
            logger.error(f"Error parsing Walmart product info: {str(e)}")
            return None