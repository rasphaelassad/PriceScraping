from typing import Dict, List, Optional, Any
import json
import logging
import traceback
from datetime import datetime, timezone
from .base_scraper import BaseScraper

logger = logging.getLogger(__name__)

class AlbertsonsScraper(BaseScraper):
    """Scraper implementation for Albertsons."""

    def __init__(self):
        """Initialize the scraper in async mode."""
        super().__init__(mode="async")  # Use async parallel mode instead of batch
        logger.info("Initialized AlbertsonsScraper in async mode")
    
    def get_scraper_config(self) -> Dict[str, Any]:
        """Return scraper configuration for Albertsons."""
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

    async def extract_product_info(self, html: str, url: str) -> Optional[Dict[str, Any]]:
        """
        Extract product information from Albertsons API response.
        
        Args:
            html: The JSON response content to extract information from.
            url: The URL the content was fetched from.
            
        Returns:
            A dictionary containing product information, or None if extraction failed.
        """
        try:
            # Parse the JSON response
            try:
                data = json.loads(html)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON response: {e}")
                logger.error(traceback.format_exc())
                return None
            
            # Get the product from catalog response
            catalog = data.get('catalog', {})
            if not catalog:
                logger.error("No catalog data found in response")
                return None
                
            response = catalog.get('response', {})
            if not response:
                logger.error("No response data found in catalog")
                return None
                
            docs = response.get('docs', [])
            if not docs:
                logger.error("No product documents found in response")
                return None
                
            product = docs[0]
            if not product:
                logger.error("No product found in catalog response")
                return None
            
            # Extract required fields
            product_id = product.get('pid')
            if not product_id:
                logger.error("No product ID found")
                return None
                
            name = product.get('name')
            if not name:
                logger.error("No product name found")
                return None
            
            # Extract price information
            price = None
            price_string = None
            try:
                price = float(product.get('price', 0))
                if price > 0:
                    price_string = f"${price}"
            except (ValueError, TypeError) as e:
                logger.warning(f"Error converting price: {e}")
            
            # Extract price per unit information
            price_per_unit = None
            price_per_unit_string = None
            try:
                price_per = product.get('pricePer')
                if price_per:
                    price_per_unit = float(price_per)
                    price_per_unit_string = f"${price_per}/Lb"
            except (ValueError, TypeError) as e:
                logger.warning(f"Error converting price per unit: {e}")
            
            # Extract store information
            store_id = product.get('storeId')
            
            # Extract location information
            store_address = None
            store_zip = None
            try:
                location = product.get('location', {})
                if location:
                    address = location.get('address', {})
                    if address:
                        store_address = address.get('streetAddress')
                        store_zip = address.get('postalCode')
            except Exception as e:
                logger.warning(f"Error extracting location information: {e}")
            
            # Extract brand information
            brand = None
            try:
                brand_info = product.get('brand', {})
                if isinstance(brand_info, dict):
                    brand = brand_info.get('name')
            except Exception as e:
                logger.warning(f"Error extracting brand information: {e}")
            
            # Extract category information
            category = None
            try:
                department = product.get('departmentName', '')
                shelf = product.get('shelfName', '')
                if department or shelf:
                    parts = []
                    if department:
                        parts.append(department)
                    if shelf:
                        parts.append(shelf)
                    category = "/".join(parts)
            except Exception as e:
                logger.warning(f"Error extracting category information: {e}")
            
            # Build the standardized product information
            product_info = {
                "store": "albertsons",
                "url": f"https://www.albertsons.com/shop/product-details.{product_id}.html",
                "name": name,
                "price": price,
                "price_string": price_string,
                "price_per_unit": price_per_unit,
                "price_per_unit_string": price_per_unit_string,
                "store_id": store_id,
                "store_address": store_address,
                "store_zip": store_zip,
                "brand": brand,
                "sku": product_id,
                "category": category,
                "timestamp": datetime.now(timezone.utc)
            }

            logger.info(f"Successfully extracted product info: {product_info}")
            return product_info

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            logger.error(traceback.format_exc())
            return None
        except Exception as e:
            logger.error(f"Error extracting product info: {e}")
            logger.error(traceback.format_exc())
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
        # Store original URLs
        original_urls = [str(url) for url in urls]
        
        # Transform URLs to API format
        api_urls = [self.transform_url(url) for url in urls]
        
        # Call parent implementation with transformed URLs
        results = await super().get_prices(api_urls)
        
        # Map results back to original URLs
        original_results = {}
        for orig_url, api_url in zip(original_urls, api_urls):
            if api_url in results and results[api_url]:
                # Ensure the result uses the original product URL
                result = results[api_url].copy()
                result['url'] = orig_url
                original_results[orig_url] = result
            else:
                original_results[orig_url] = None
                
        return original_results