from typing import Dict, List, Optional
import json
import logging
from datetime import datetime, timezone
from .base_scraper import BaseScraper
from parsel import Selector
import re

logger = logging.getLogger(__name__)

class AlbertsonsScraper(BaseScraper):
    def __init__(self):
        super().__init__(mode="async")  # Use async parallel mode instead of batch
        self.store_name = "albertsons"  # Set store name in lowercase to match database entries
    
    def get_scraper_config(self) -> dict:
        """Get Albertsons-specific scraper configuration."""
        return {
            "premium": True,
            "country_code": "us",
            "device_type": "desktop",
            "keep_headers": True,
            "headers": {
                "Accept": "application/json",
                "Accept-Language": "en-US,en;q=0.5"
            }
        }

    def transform_url(self, url: str) -> str:
        """Transform Albertsons product URL to API URL."""
        try:
            # Extract product ID from URL
            product_id = re.search(r'product-details\.(\d+)\.html', url)
            if not product_id:
                logger.error(f"Could not extract product ID from URL: {url}")
                return url
                
            # Convert to API URL
            api_url = f"https://www.albertsons.com/abs/pub/xapi/v1/product/{product_id.group(1)}"
            logger.info(f"Transformed URL {url} to {api_url}")
            return api_url
        except Exception as e:
            logger.error(f"Error transforming URL {url}: {e}")
            return url

    async def extract_product_info(self, html: str, url: str) -> Optional[Dict]:
        """Extract product information from Albertsons API response."""
        try:
            data = json.loads(html)
            product = data.get("product", {})
            
            if not product:
                logger.error("No product data found in API response")
                return None

            # Extract basic info
            name = product.get("name")
            if not name:
                logger.error("No product name found")
                return None

            # Extract price info
            price_info = product.get("price", {})
            price = price_info.get("regularPrice")
            price_string = f"${price}" if price else None

            # Extract store info
            store_info = product.get("storeInfo", {})
            store_id = store_info.get("storeId")
            store_address = store_info.get("address", {}).get("line1")
            store_zip = store_info.get("address", {}).get("zipCode")

            # Extract additional info
            brand = product.get("brand")
            sku = product.get("sku")
            category = product.get("category", {}).get("name")

            return {
                "store": "albertsons",
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

    async def get_prices(self, urls: List[str]) -> Dict[str, Optional[Dict]]:
        """Get prices for multiple URLs"""
        # Store original URLs
        original_urls = [str(url) for url in urls]
        
        # Transform URLs to API format
        api_urls = []
        url_mapping = {}  # Keep track of which API URL maps to which original URL
        
        for url in original_urls:
            api_url = self.transform_url(url)
            api_urls.append(api_url)
            url_mapping[api_url] = url
        
        # Call parent implementation with transformed URLs
        results = await super().get_prices(api_urls)
        
        # Map results back to original URLs
        original_results = {}
        for orig_url in original_urls:
            api_url = self.transform_url(orig_url)
            if api_url in results and results[api_url]:
                # Ensure the result uses the original product URL
                result = results[api_url].copy()
                result['url'] = orig_url
                original_results[orig_url] = result
            else:
                original_results[orig_url] = None
                
        return original_results