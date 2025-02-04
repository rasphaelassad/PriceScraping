from typing import Dict, Optional
from ..base import BaseScraper
import json
from parsel import Selector
import logging

logger = logging.getLogger(__name__)

class ChefStoreScraper(BaseScraper):
    """Scraper for ChefStore products."""
    
    store_name = "chefstore"
    url_pattern = r"(?:www\.)?chefstore\.com"
    
    def get_scraper_config(self) -> dict:
        """Get ChefStore-specific scraper configuration."""
        return {
            "country_code": "us",
            "keep_headers": "true",
            "headers": {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5"
            }
        }

    async def extract_product_info(self, html: str, url: str) -> Optional[Dict]:
        """Extract product information from ChefStore HTML."""
        try:
            selector = Selector(text=html)
            
            # Extract product data from script tag
            script = selector.css('script[type="application/ld+json"]::text').get()
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
            price = data.get("offers", {}).get("price")
            price_string = f"${price}" if price else None

            # Extract price per unit info
            unit_pricing = data.get("offers", {}).get("unitPricing", {})
            price_per_unit = unit_pricing.get("price", {}).get("value")
            price_per_unit_string = f"${price_per_unit} per {unit_pricing.get('unitText')}" if price_per_unit else None

            # Extract additional info
            brand = data.get("brand", {}).get("name")
            sku = data.get("sku")
            category = data.get("category")

            # Extract store info from meta tags
            store_id = selector.css('meta[property="business:contact_data:store_code"]::attr(content)').get()
            store_address = selector.css('meta[property="business:contact_data:street_address"]::attr(content)').get()
            store_zip = selector.css('meta[property="business:contact_data:postal_code"]::attr(content)').get()

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