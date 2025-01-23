import logging
import re
import urllib.parse
from bs4 import BeautifulSoup
from typing import Dict, Optional, Tuple

from pydantic_core import Url
from .base_scraper import BaseScraper, logger
import os
from datetime import datetime


class CostcoScraper(BaseScraper):
    def get_scraper_config(self) -> dict:
        return {
            "premium": False,
            #"render": True,
            "country_code": "us",
            "device_type": "desktop",
            "keep_headers": True,
            "headers": {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "zip_code": "28115"
            }
        }

    def _extract_price_from_element(self, price_element) -> Tuple[Optional[float], Optional[str]]:
        """Extract price and price string from a price element."""
        if not price_element:
            return None, None
            
        price_text = price_element.get_text()
        logger.info(f"Found price text: {price_text}")
        
        price_match = re.search(r'\$(\d+\.\d+)', price_text)
        if price_match:
            price = float(price_match.group(1))
            price_string = f"${price}"
            logger.info(f"Extracted price: {price}")
            return price, price_string
        
        return None, None

    def _extract_data_from_scripts(self, soup) -> Tuple[Optional[float], Optional[str], Optional[str]]:
        """Extract price per unit and delivery location from script tags."""
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
        
        return price_per_unit, price_per_unit_string, delivery_location

    async def extract_product_info(self, html: str, url: str) -> Dict:
        """Extract product information from Costco HTML content."""
        try:
            logger.info(f"Starting to extract product info for URL: {url}")
            logger.info(f"HTML length: {len(html)}")
            
            #saving HTML locally
            # Create directory if it doesn't exist
            os.makedirs('sample_files/costco', exist_ok=True)

            # Create filename with timestamp
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f'costco_{timestamp}.html'
            filepath = os.path.join('sample_files', 'costco', filename)

            # Save the HTML content
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(html)

            print(f'File saved to: {filepath}')

            soup = BeautifulSoup(html, 'html.parser')
            
            # Extract price from visible elements
            price, price_string = self._extract_price_from_element(soup.find('div', class_='e-1wia3ii'))
            
            # Extract price per unit and delivery location from scripts
            price_per_unit, price_per_unit_string, delivery_location = self._extract_data_from_scripts(soup)
            
            # Extract product name
            title_element = soup.find('span', class_='e-1y16mcr')
            name = title_element.get_text().strip() if title_element else None
            logger.info(f"Extracted name: {name}")
            
            product_info = {
                'store': 'costco',
                'url': Url,
                'name': name,
                'price': price,
                'price_string': price_string,
                'price_per_unit': price_per_unit,
                'price_per_unit_string': price_per_unit_string,
                'delivery_location': delivery_location
            }
            
            logger.info(f"Successfully extracted product info: {product_info}")
            return product_info
            
        except Exception as e:
            logger.error(f"Error parsing Costco product info: {str(e)}")
            return None 