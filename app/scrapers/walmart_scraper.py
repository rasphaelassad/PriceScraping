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

            price_info = product.get("priceInfo", {}).get("unitPrice", {})
            price = price_info.get("price")
            price_string = price_info.get("priceString")
            name = product.get("name")

            result = {
                "store": "walmart",
                "url": url,
                "name": name,
                "price": float(price) if price else None,
                "price_string": price_string
            }
            
            return result
        except Exception as e:
            logger.error(f"Error parsing Walmart product info: {str(e)}")
            return None

    # Keep the extract_price method for backward compatibility if needed
    async def extract_price(self, html: str) -> float:
        product_info = await self.extract_product_info(html, "")
        return product_info.get("price") if product_info else None 