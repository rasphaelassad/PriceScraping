from typing import Dict, List, Optional
import json
import logging
from datetime import datetime, timezone
from .base_scraper import BaseScraper

logger = logging.getLogger(__name__)

class AlbertsonsScraper(BaseScraper):
    def __init__(self):
        super().__init__(mode="async")  # Use async parallel mode instead of batch
        self.store_name = "albertsons"  # Set store name in lowercase to match database entries
    
    def get_scraper_config(self) -> Dict:
        """Return scraper configuration for Albertsons"""
        return {
            "headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Accept": "application/json",
                "Accept-Language": "en-US,en;q=0.9",
                "ocp-apim-subscription-key": "6c21edb7bcda4f0e918348db16147431"
            },
            "country": "us",
            "keepHeaders": True,
            "render": False  # Disable JS rendering since we're using an API
        }

    async def extract_product_info(self, html: str, url: str) -> Optional[Dict]:
        """Extract product information from Albertsons API response"""
        try:
            # Parse the JSON response
            data = json.loads(html)
            
            # Get the product from catalog response
            product = data.get('catalog', {}).get('response', {}).get('docs', [{}])[0]
            if not product:
                logger.error(f"No product found in catalog response for URL: {url}")
                return None
            
            # Extract price information safely
            try:
                price = float(product.get('price', 0))
                price_per_unit = float(product.get('pricePer', 0)) if product.get('pricePer') else None
            except (ValueError, TypeError) as e:
                logger.error(f"Error parsing price values for URL {url}: {e}")
                price = 0.0
                price_per_unit = None
            
            # Build the standardized product information
            product_info = {
                "store": self.store_name,  # Use store_name from instance for consistency
                "url": url,  # Use the original URL passed to the method
                "name": product.get('name'),
                "price": price,
                "price_string": f"${price:.2f}",
                "price_per_unit": price_per_unit,
                "price_per_unit_string": f"${price_per_unit:.2f}/Lb" if price_per_unit else None,
                "store_id": product.get('storeId'),
                "store_address": None,  # Not available in this API response
                "store_zip": None,  # Not available in this API response
                "brand": product.get('brandName'),  # Added brand name from API
                "sku": product.get('pid'),
                "category": f"{product.get('departmentName', '')}/{product.get('shelfName', '')}".strip('/'),
                "timestamp": datetime.now(timezone.utc)
            }

            logger.info(f"Successfully extracted product info for {url}")
            logger.debug(f"Product info: {product_info}")
            return product_info

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response for URL {url}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error extracting product info for URL {url}: {e}")
            return None

    def transform_url(self, url: str) -> str:
        """Transform product detail URL to API URL"""
        try:
            if "product-details." not in url:
                logger.warning(f"Invalid URL format: {url}")
                return url
                
            # Extract product ID from URL
            product_id = url.split("product-details.")[-1].split(".")[0].strip()
            if not product_id.isdigit():
                logger.warning(f"Invalid product ID in URL: {url}")
                return url
                
            # Transform to API URL format
            return f"https://www.albertsons.com/abs/pub/xapi/product/v2/pdpdata?bpn={product_id}&banner=albertsons&storeId=177"
        except Exception as e:
            logger.error(f"Error transforming URL {url}: {e}")
            return url

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