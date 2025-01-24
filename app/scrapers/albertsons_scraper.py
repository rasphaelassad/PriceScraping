from typing import Dict, List
import json
import logging
from .base_scraper import BaseScraper

logger = logging.getLogger(__name__)

class AlbertsonsScraper(BaseScraper):
    def __init__(self):
        super().__init__(mode="async")  # Use async parallel mode instead of batch
    
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
            "keepHeaders": True
        }

    async def extract_product_info(self, html: str, url: str) -> Dict:
        """Extract product information from Albertsons API response"""
        try:
            # Parse the JSON response
            data = json.loads(html)
            
            # Get the product from catalog response
            product = data.get('catalog', {}).get('response', {}).get('docs', [{}])[0]
            if not product:
                logger.error("No product found in catalog response")
                return None
            
            # Build the standardized product information
            product_info = {
                "store": "Albertsons",
                "url": f"https://www.albertsons.com/shop/product-details.{product.get('pid')}.html",
                "name": product.get('name'),
                "price": float(product.get('price', 0)),
                "price_string": f"${product.get('price', '0')}",
                "price_per_unit": float(product.get('pricePer', 0)) if product.get('pricePer') else None,
                "price_per_unit_string": f"${product.get('pricePer', '0')}/Lb" if product.get('pricePer') else None,
                "store_id": product.get('storeId'),
                "store_address": None,  # Not available in this API response
                "store_zip": None,  # Not available in this API response
                "brand": None,  # Not directly available in this response
                "sku": product.get('pid'),
                "category": f"{product.get('departmentName', '')}/{product.get('shelfName', '')}"
            }

            logger.info(f"Successfully extracted product info: {product_info}")
            return product_info

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            return None
        except Exception as e:
            logger.error(f"Error extracting product info: {e}")
            return None

    def transform_url(self, url) -> str:
        """Transform product detail URL to API URL"""
        # Convert Pydantic Url to string
        url = str(url)
        
        if "product-details." in url:
            # Extract product ID from URL
            product_id = url.split("product-details.")[-1].split(".")[0]
            # Transform to API URL format
            return f"https://www.albertsons.com/abs/pub/xapi/product/v2/pdpdata?bpn={product_id}&banner=albertsons&storeId=177"
        return url

    async def get_prices(self, urls: List[str]) -> Dict[str, Dict]:
        """Override to transform URLs before processing"""
        # Transform all URLs to API format
        api_urls = [self.transform_url(url) for url in urls]
        
        # Call parent implementation with transformed URLs
        results = await super().get_prices(api_urls)
        
        # Map results back to original URLs
        return dict(zip([str(url) for url in urls], results.values()))