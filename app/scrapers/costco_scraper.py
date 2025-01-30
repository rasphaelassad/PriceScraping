import logging
import re
import urllib.parse
from bs4 import BeautifulSoup
from typing import Dict, Optional, Any, Tuple
from datetime import datetime, timezone
import traceback
from .base_scraper import BaseScraper, logger
import os
import json
import httpx
import uuid

class CostcoScraper(BaseScraper):
    """Scraper implementation for Costco."""

    def __init__(self, mode: str = "batch"):
        super().__init__(mode)
        self.store_name = "costco"

    def get_scraper_config(self) -> Dict:
        return {
            "country": "us",
            "render": "true",  # Costco requires JavaScript rendering
            "headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
        }

    def _extract_price_from_element(self, price_element) -> Tuple[Optional[float], Optional[str]]:
        """Extract price and price string from a price element.

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
        """Extract price per unit and delivery location from script tags.

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
                    
                    if not price_per_unit:
                        price_per_unit_match = re.search(r'pricingUnitString":\s*"\$(\d+\.\d+)\s*/\s*lb"', decoded_content)
                        if price_per_unit_match:
                            price_per_unit = float(price_per_unit_match.group(1))
                            price_per_unit_string = f"${price_per_unit} /lb"
                            logger.info(f"Found price per unit in script: {price_per_unit_string}")
                    
                    if not delivery_location:
                        location_match = re.search(r'postalCode":\s*"(\d{5})"', decoded_content)
                        if location_match:
                            delivery_location = location_match.group(1)
                            logger.info(f"Found delivery location in script: {delivery_location}")
                    
                    if price_per_unit and delivery_location:
                        break
                except Exception as e:
                    logger.warning(f"Error processing script tag: {e}")
                    continue
        except Exception as e:
            logger.error(f"Error extracting data from scripts: {e}")
            logger.error(traceback.format_exc())
            return None, None, None
            
        return price_per_unit, price_per_unit_string, delivery_location

    async def extract_product_info(self, html: str, url: str) -> Optional[Dict]:
        """Extract product information from HTML content.

        Args:
            html (str): Raw HTML content
            url (str): Product URL

        Returns:
            Optional[Dict]: Extracted product information or None if extraction failed
        """
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Extract product name
            name_element = soup.select_one('h1.product-name')
            if not name_element:
                logger.warning("Could not find product name")
                return None
            
            name = name_element.get_text().strip()
            
            # Extract price
            price_element = soup.select_one('div.price span.price')
            price, price_string = self._extract_price_from_element(price_element)
            
            if not price:
                logger.warning("Could not extract price")
                return None
            
            # Extract additional data from scripts
            price_per_unit, price_per_unit_string, delivery_location = self._extract_data_from_scripts(soup)
            
            # Extract product number (SKU)
            sku_element = soup.select_one('div.product-info-specs span.product-info-item-value')
            sku = sku_element.get_text().strip() if sku_element else None
            
            return {
                "store": "costco",
                "url": url,
                "name": name,
                "price": price,
                "price_string": price_string,
                "price_per_unit": price_per_unit,
                "price_per_unit_string": price_per_unit_string,
                "store_zip": delivery_location,
                "sku": sku
            }
            
        except Exception as e:
            logger.error(f"Error extracting Costco product info: {str(e)}")
            logger.error(traceback.format_exc())
            return None
