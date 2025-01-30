import logging
import re
import urllib.parse
from bs4 import BeautifulSoup
from typing import Dict, Optional, Tuple
from .base_scraper import BaseScraper, logger

class CostcoScraper(BaseScraper):
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

    async def extract_product_info(self, html: str, url: str) -> Optional[Dict]:
        """Extract product information from Costco HTML content."""
        try:
            logger.info(f"Starting to extract product info for URL: {url}")
            soup = BeautifulSoup(html, 'html.parser')
            
            # Extract price from visible elements
            price_element = soup.find('div', class_='e-1wia3ii')
            price = None
            price_string = None
            
            if price_element:
                price_text = price_element.get_text()
                logger.info(f"Found price text: {price_text}")
                price_match = re.search(r'\$(\d+\.\d+)', price_text)
                if price_match:
                    price = float(price_match.group(1))
                    price_string = f"${price}"
                    logger.info(f"Extracted price: {price}")

            # Extract additional information from script tags
            price_per_unit = None
            price_per_unit_string = None
            delivery_location = None
            
            for script in soup.find_all('script'):
                if not script.string:
                    continue
                    
                decoded_content = urllib.parse.unquote(script.string)
                
                # Look for price per pound
                if not price_per_unit:
                    price_per_unit_match = re.search(r'pricingUnitString":\s*"\$(\d+\.\d+)\s*/\s*lb"', decoded_content)
                    if price_per_unit_match:
                        price_per_unit = float(price_per_unit_match.group(1))
                        price_per_unit_string = f"${price_per_unit} /lb"
                        logger.info(f"Found price per unit in script: {price_per_unit_string}")
                
                # Look for delivery location
                if not delivery_location:
                    location_match = re.search(r'postalCode":\s*"(\d{5})"', decoded_content)
                    if location_match:
                        delivery_location = location_match.group(1)
                        logger.info(f"Found delivery location in script: {delivery_location}")
                
                # Break if we found both pieces of information
                if price_per_unit and delivery_location:
                    break
            
            # Extract product name
            name_element = soup.find('h1', class_='product-name')
            name = name_element.get_text().strip() if name_element else None
            
            # Extract product ID/SKU
            sku = None
            sku_element = soup.find('div', {'automation-id': 'productItemNumber'})
            if sku_element:
                sku_match = re.search(r'Item (\d+)', sku_element.get_text())
                if sku_match:
                    sku = sku_match.group(1)
            
            # Extract brand
            brand_element = soup.find('div', class_='product-brand')
            brand = brand_element.get_text().strip() if brand_element else None
            
            # Build the standardized product information
            product_info = {
                "store": "Costco",
                "url": url,
                "name": name,
                "price": price,
                "price_string": price_string,
                "price_per_unit": price_per_unit,
                "price_per_unit_string": price_per_unit_string,
                "store_id": None,  # Not available in HTML
                "store_address": None,  # Not available in HTML
                "store_zip": delivery_location,
                "brand": brand,
                "sku": sku,
                "category": None  # Not reliably available in HTML
            }
            
            logger.info(f"Successfully extracted product info: {product_info}")
            return product_info

        except Exception as e:
            logger.error(f"Error extracting product info: {e}")
            return None