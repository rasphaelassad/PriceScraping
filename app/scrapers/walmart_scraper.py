import json
from parsel import Selector
from .base_scraper import BaseScraper, logger
from typing import Dict, Optional, Any
from datetime import datetime, timezone
import traceback
import time
from bs4 import BeautifulSoup
import re
import httpx
import uuid

class WalmartScraper(BaseScraper):
    """Scraper implementation for Walmart."""

    def __init__(self, mode: str = "batch"):
        super().__init__(mode)
        self.store_name = "walmart"

    def get_scraper_config(self) -> Dict:
        return {
            "country": "us",
            #"render": "true",  # Walmart requires JavaScript rendering
            "headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
        }

    async def extract_product_info(self, html: str, url: str) -> Optional[Dict]:
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Find product data in script tag
            script_tags = soup.find_all('script', {'type': 'application/ld+json'})
            product_data = None
            for tag in script_tags:
                try:
                    data = json.loads(tag.string)
                    if isinstance(data, dict) and data.get('@type') == 'Product':
                        product_data = data
                        break
                except:
                    continue
            
            if not product_data:
                return None

            # Extract price
            price_elem = soup.select_one('[itemprop="price"]')
            price_string = price_elem.get('content') if price_elem else None
            price = float(price_string) if price_string else None
            
            return {
                "store": "walmart",
                "url": url,
                "name": product_data.get('name'),
                "price": price,
                "price_string": f"${price}" if price else None,
                "brand": product_data.get('brand', {}).get('name'),
                "sku": product_data.get('sku')
            }
            
        except Exception as e:
            logger.error(f"Error extracting Walmart product info: {str(e)}")
            return None
