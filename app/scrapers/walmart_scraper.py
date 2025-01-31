
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
            selector = Selector(text=html)
            next_data = selector.css("script#__NEXT_DATA__::text").get()
            if not next_data:
                return None

            import json
            data = json.loads(next_data)
            product = (
                data.get("props", {})
                    .get("pageProps", {})
                    .get("initialData", {})
                    .get("data", {})
                    .get("product", {})
            )

            price_info = product.get("priceInfo", {}).get("unitPrice", {})
            return {
                "store": "walmart",
                "url": url,
                "name": product.get("name"),
                "price": float(price_info.get("price")) if price_info.get("price") else None,
                "price_string": price_info.get("priceString")
            }
        except Exception as e:
            logger.error(f"Error parsing Walmart product info: {str(e)}")
            return None
