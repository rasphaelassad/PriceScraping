import asyncio
from typing import Dict, Optional, List
from ..base import BaseScraper
import json
import logging
from parsel import Selector
import re

logger = logging.getLogger(__name__)

class AlbertsonsScraper(BaseScraper):
    """Scraper for Albertsons products."""
    
    store_name = "albertsons"
    
    def get_scraper_config(self) -> dict:
        """Get Albertsons-specific scraper configuration."""
        return {
            "premium": False,
            "country_code": "us",
            "render": False,
            "keep_headers": True,
            "headers": {
                "Accept": "application/json",
                "Accept-Language": "en-US,en;q=0.5",
                "ocp-apim-subscription-key": "6c21edb7bcda4f0e918348db16147431"
            }
        }

    async def get_prices(self, urls: List[str], store_id: str) -> List[Optional[Dict]]:
        """Fetch and extract prices for Albertsons products asynchronously."""
        async def fetch_and_extract(url: str):
            try:
                api_url = self.transform_url(url, store_id)
                fetch_result = await self.fetch_data_async_from_scraperapi(api_url)
                return await self.extract_product_info(fetch_result['content'], url)
            except Exception as e:
                logger.error(f"Error processing URL {url}: {e}")
                return None

        return await asyncio.gather(*(fetch_and_extract(url) for url in urls))



    def transform_url(self, url: str, store_id: str) -> str:
        """Transform Albertsons product URL to API URL."""
        try:
            # Extract product ID from URL
            product_id = re.search(r'product-details\.(\d+)\.html', url)
            if not product_id:
                logger.error(f"Could not extract product ID from URL: {url}")
                return url
                
            # Convert to API URL
            api_url = f"https://www.albertsons.com/abs/pub/xapi/product/v2/pdpdata?bpn={product_id.group(1)}&banner=albertsons&storeId={store_id}"
            logger.info(f"Transformed URL {url} to {api_url}")
            return api_url
        except Exception as e:

            logger.error(f"Error transforming URL {url}: {e}")
            return url

    async def extract_product_info(self, html: str, url: str) -> Optional[Dict]:
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
                "url": url,
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