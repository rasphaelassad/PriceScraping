import logging
import re
import urllib.parse
from bs4 import BeautifulSoup
from typing import Dict, Optional, Any, Tuple
from datetime import datetime, timezone
import traceback
from .base_scraper import BaseScraper, logger
import os


class CostcoScraper(BaseScraper):
    """Scraper implementation for Costco."""

    def get_scraper_config(self) -> Dict[str, Any]:
        """Return scraper configuration for Costco."""
        return {
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

    def _extract_price_from_element(self, price_element) -> Tuple[Optional[float], Optional[str]]:
        """
        Extract price and price string from a price element.
        
        Args:
            price_element: The HTML element containing the price.
            
        Returns:
            A tuple of (price, price_string) where price is a float and price_string is the formatted price.
        """
        if not price_element:
            logger.debug("No price element found")
            return None, None
            
        try:
            price_text = price_element.get_text()
            logger.info(f"Found price text: {price_text}")
            
            price_match = re.search(r'\$(\d+\.\d+)', price_text)
            if price_match:
                price = float(price_match.group(1))
                price_string = f"${price}"
                logger.info(f"Extracted price: {price}")
                return price, price_string
            else:
                logger.warning(f"Could not extract price from text: {price_text}")
                return None, None
        except Exception as e:
            logger.error(f"Error extracting price: {e}")
            logger.error(traceback.format_exc())
            return None, None

    def _extract_data_from_scripts(self, soup: BeautifulSoup) -> Tuple[Optional[float], Optional[str], Optional[str]]:
        """
        Extract price per unit and delivery location from script tags.
        
        Args:
            soup: The BeautifulSoup object containing the HTML.
            
        Returns:
            A tuple of (price_per_unit, price_per_unit_string, delivery_location).
        """
        price_per_unit = None
        price_per_unit_string = None
        delivery_location = None
        
        try:
            for script in soup.find_all('script'):
                if not script.string:
                    continue
                    
                try:
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
                except Exception as e:
                    logger.warning(f"Error processing script tag: {e}")
                    continue
        except Exception as e:
            logger.error(f"Error extracting data from scripts: {e}")
            logger.error(traceback.format_exc())
        
        return price_per_unit, price_per_unit_string, delivery_location

    async def extract_product_info(self, html: str, url: str) -> Optional[Dict[str, Any]]:
        """
        Extract product information from Costco HTML content.
        
        Args:
            html: The HTML content to extract information from.
            url: The URL the content was fetched from.
            
        Returns:
            A dictionary containing product information, or None if extraction failed.
        """
        try:
            logger.info(f"Starting to extract product info for URL: {url}")
            logger.info(f"HTML length: {len(html)}")
            
            # Save HTML locally for debugging
            try:
                os.makedirs('sample_files/costco', exist_ok=True)
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f'costco_{timestamp}.html'
                filepath = os.path.join('sample_files', 'costco', filename)
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(html)
                logger.debug(f'HTML saved to: {filepath}')
            except Exception as e:
                logger.warning(f"Failed to save HTML file: {e}")

            soup = BeautifulSoup(html, 'html.parser')
            
            # Extract price from visible elements
            price_element = soup.find('div', class_='e-1wia3ii')
            price, price_string = self._extract_price_from_element(price_element)
            
            if not price:
                logger.warning("No price found in visible elements")
                # Try alternate price element
                price_element = soup.find('div', class_='product-price')
                price, price_string = self._extract_price_from_element(price_element)
            
            # Extract price per unit and delivery location from scripts
            price_per_unit, price_per_unit_string, delivery_location = self._extract_data_from_scripts(soup)
            
            # Extract product name
            title_element = soup.find('span', class_='e-1y16mcr')
            if not title_element:
                title_element = soup.find('h1', class_='product-title')
            name = title_element.get_text().strip() if title_element else None
            
            if not name:
                logger.error("No product name found")
                return None
                
            logger.info(f"Extracted name: {name}")
            
            # Extract additional information
            brand = None
            brand_element = soup.find('div', class_='product-brand')
            if brand_element:
                brand = brand_element.get_text().strip()
            
            sku = None
            sku_element = soup.find('div', class_='product-sku')
            if sku_element:
                sku_match = re.search(r'Item\s+#\s*(\d+)', sku_element.get_text())
                if sku_match:
                    sku = sku_match.group(1)
            
            category = None
            breadcrumbs = soup.find('nav', class_='breadcrumb')
            if breadcrumbs:
                category_elements = breadcrumbs.find_all('a')
                if category_elements:
                    category = " > ".join(elem.get_text().strip() for elem in category_elements[1:])
            
            product_info = {
                'store': 'costco',
                'url': url,
                'name': name,
                'price': price,
                'price_string': price_string,
                'price_per_unit': price_per_unit,
                'price_per_unit_string': price_per_unit_string,
                'store_zip': delivery_location,
                'brand': brand,
                'sku': sku,
                'category': category,
                'timestamp': datetime.now(timezone.utc)
            }
            
            logger.info(f"Successfully extracted product info: {product_info}")
            return product_info
            
        except Exception as e:
            logger.error(f"Error parsing Costco product info: {e}")
            logger.error(traceback.format_exc())
            return None 