from parsel import Selector
from .base_scraper import BaseScraper, logger
from typing import Dict, Optional, Any
import json
from datetime import datetime, timezone
import traceback
import re

class ChefStoreScraper(BaseScraper):
    """Scraper implementation for ChefStore."""

    def get_scraper_config(self) -> Dict[str, Any]:
        """Return scraper configuration for ChefStore."""
        return {
            'max_cost': '30',
            "retry_times": 3,
            "premium": False,
            "country_code": "us",
            "device_type": "desktop",
            "keep_headers": True,
            "headers": {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
        }

    async def extract_product_info(self, html: str, url: str) -> Optional[Dict[str, Any]]:
        """
        Extract product information from ChefStore HTML content.
        
        Args:
            html: The HTML content to extract information from.
            url: The URL the content was fetched from.
            
        Returns:
            A dictionary containing product information, or None if extraction failed.
        """
        try:
            logger.info(f"Starting to extract product info for URL: {url}")
            selector = Selector(text=html)
            
            # Get JSON-LD script content
            scripts = selector.css('script[type="application/ld+json"]::text').get()
            if not scripts:
                logger.error("Could not find JSON-LD script in HTML")
                return None
            
            logger.info("Found JSON-LD script, parsing JSON")
            try:
                data = json.loads(scripts)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON data: {e}")
                return None
            
            if not data:
                logger.error("Empty JSON data")
                return None
            
            # Extract store information
            store_link = selector.css('a.store-address-link::attr(href)').get()
            store_id = None
            store_address = None
            store_zip = None
            
            try:
                if store_link:
                    # Extract store ID from URL
                    store_id_match = re.search(r'/store/(\d+)/', store_link)
                    if store_id_match:
                        store_id = store_id_match.group(1)
                    
                    # Get store address
                    store_address = selector.css('a.store-address-link::text').get()
                    if store_address:
                        store_address = store_address.strip()
                        # Try to extract ZIP code from address
                        zip_match = re.search(r'\b\d{5}(?:-\d{4})?\b', store_address)
                        if zip_match:
                            store_zip = zip_match.group(0)
            except Exception as e:
                logger.warning(f"Error extracting store information: {e}")
            
            # Extract price information
            price = None
            price_string = None
            price_per_unit = None
            price_per_unit_string = None
            
            if "offers" in data:
                offers = data["offers"]
                if isinstance(offers, dict):
                    # Try high price first, then regular price
                    if "highPrice" in offers:
                        price = float(offers["highPrice"])
                    elif "price" in offers:
                        price = float(offers["price"])
                    
                    if price is not None:
                        price_string = f"${price}"
                        
                        # Try to extract price per unit
                        unit_price_element = selector.css('.unit-price::text').get()
                        if unit_price_element:
                            try:
                                unit_price_match = re.search(r'\$(\d+\.?\d*)/(\w+)', unit_price_element)
                                if unit_price_match:
                                    price_per_unit = float(unit_price_match.group(1))
                                    price_per_unit_string = unit_price_element.strip()
                            except (ValueError, AttributeError) as e:
                                logger.warning(f"Error parsing unit price: {e}")
            
            # Extract product name
            name = data.get("name")
            if not name:
                logger.error("No product name found")
                return None
            
            # Extract brand information
            brand = None
            brand_data = data.get("brand", {})
            if isinstance(brand_data, dict):
                brand = brand_data.get("name")
            
            # Extract category
            category = data.get("category")
            if not category:
                # Try to get category from breadcrumbs
                breadcrumbs = selector.css('.breadcrumb-item a::text').getall()
                if breadcrumbs:
                    # Skip first item (usually "Home")
                    category = " > ".join(crumb.strip() for crumb in breadcrumbs[1:])
            
            result = {
                "store": "chefstore",
                "url": url,
                "name": name,
                "price": price,
                "price_string": price_string,
                "price_per_unit": price_per_unit,
                "price_per_unit_string": price_per_unit_string,
                "store_id": store_id,
                "store_address": store_address,
                "store_zip": store_zip,
                "brand": brand,
                "sku": data.get("sku"),
                "category": category,
                "timestamp": datetime.now(timezone.utc)
            }
            
            logger.info(f"Successfully extracted product info: {result}")
            return result
            
        except Exception as e:
            logger.error(f"Error parsing ChefStore product info: {e}")
            logger.error(traceback.format_exc())
            return None
