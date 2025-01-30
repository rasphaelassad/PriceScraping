from typing import Dict, Optional, Any
import json
import logging
from datetime import datetime, timezone
from .base_scraper import BaseScraper
import httpx
from bs4 import BeautifulSoup
import re
import uuid

logger = logging.getLogger(__name__)

class ChefStoreScraper(BaseScraper):
    """Scraper implementation for ChefStore."""

    def __init__(self, mode: str = "batch"):
        super().__init__(mode)
        self.store_name = "chefstore"

    def get_scraper_config(self) -> Dict:
        return {
            "country": "us",
            "headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
        }

    async def extract_product_info(self, html: str, url: str) -> Optional[Dict]:
        """Extract product information from HTML content."""
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Extract product name
            name_elem = soup.find('h1', {'class': 'product-name'})
            if not name_elem:
                logger.warning("Could not find product name")
                return None
            name = name_elem.text.strip()
            
            # Extract price
            price_elem = soup.find('span', {'class': 'price-value'})
            if not price_elem:
                logger.warning("Could not find price element")
                return None
                
            price_string = price_elem.text.strip()
            try:
                price = float(re.sub(r'[^\d.]', '', price_string))
                price_string = f"${price:.2f}"
            except (ValueError, AttributeError) as e:
                logger.warning(f"Could not parse price from {price_string}: {e}")
                return None
            
            # Extract other information
            sku_elem = soup.find('span', {'class': 'product-id'})
            sku = sku_elem.text.strip() if sku_elem else None
            
            # Extract brand if available
            brand_elem = soup.find('span', {'class': 'product-brand'})
            brand = brand_elem.text.strip() if brand_elem else None
            
            # Extract category if available
            category_elem = soup.find('span', {'class': 'product-category'})
            category = category_elem.text.strip() if category_elem else None
            
            # Extract price per unit if available
            price_per_unit_elem = soup.find('span', {'class': 'price-per-unit'})
            if price_per_unit_elem:
                try:
                    price_per_unit_text = price_per_unit_elem.text.strip()
                    price_per_unit_match = re.search(r'\$(\d+\.\d+)\s*/\s*(\w+)', price_per_unit_text)
                    if price_per_unit_match:
                        price_per_unit = float(price_per_unit_match.group(1))
                        unit = price_per_unit_match.group(2)
                        price_per_unit_string = f"${price_per_unit:.2f}/{unit}"
                    else:
                        price_per_unit = None
                        price_per_unit_string = None
                except (ValueError, AttributeError) as e:
                    logger.warning(f"Could not parse price per unit: {e}")
                    price_per_unit = None
                    price_per_unit_string = None
            else:
                price_per_unit = None
                price_per_unit_string = None
            
            return {
                "store": "chefstore",
                "url": url,
                "name": name,
                "price": price,
                "price_string": price_string,
                "price_per_unit": price_per_unit,
                "price_per_unit_string": price_per_unit_string,
                "brand": brand,
                "sku": sku,
                "category": category
            }
            
        except Exception as e:
            logger.error(f"Error extracting ChefStore product info: {str(e)}")
            return None
