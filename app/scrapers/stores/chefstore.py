from typing import Dict, Optional, List

import requests
from ..base import BaseScraper
import json
from parsel import Selector
import logging
import asyncio
import re

logger = logging.getLogger(__name__)

class ChefStoreScraper(BaseScraper):
    """Scraper for ChefStore products."""
    
    store_name = "chefstore"
    
    def get_scraper_config(self) -> dict:
        """Get ChefStore-specific scraper configuration."""
        return {
            "country_code": "us",
            "keep_headers": "true",
            "headers": {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5"
            }
        }
    
    async def get_prices(self, urls: List[str], store_id: str) -> List[Optional[Dict]]:
        """Fetch and extract prices for ChefStore products asynchronously."""
        proxies = {"http": "http://scraperapi:APIKEY@proxy-server.scraperapi.com:8001"}
        session = requests.Session()
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9"
        }
        session.headers.update(headers)
        set_store_url = "https://www.chefstore.com/cfcs/accountDAO.cfc?method=setStoreSessionAjax&storeNum=" + store_id + "&_=1738632451401"
        response = session.get(set_store_url, proxies=proxies)
        # check response
        if response.status_code == 200:
            logger.info("Store session request successful")
        
        async def fetch_and_extract(url: str):
            try:
                fetch_result = session.get(url, headers=headers, proxies=proxies)
                if fetch_result.status_code == 200:
                    return await self.extract_product_info(fetch_result.text, url)
            except Exception as e:
                logger.error(f"Error processing URL {url}: {e}")
                return None

        return await asyncio.gather(*(fetch_and_extract(url) for url in urls))

    def transform_url(self, url: str, store_id: str) -> str:
        """Transform ChefStore product URL to API URL."""
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
        """Extract product information from ChefStore HTML."""
        try:
            selector = Selector(text=html)
            
            # Extract product data from script tag
            scripts = selector.css('script[type="application/ld+json"]::text').get()
            if not scripts:
                logger.error("Could not find JSON-LD script in HTML")
                return None
            
            logger.info("Found JSON-LD script, parsing JSON")
            data = json.loads(scripts)
            
            # Extract store information
            store_link = selector.css('a.store-address-link::attr(href)').get()
            store_id = store_link.split('/')[-2] if store_link else None
            store_address = selector.css('a.store-address-link::text').get()
            
            # Extract price information from product-widget div
            product_widget = selector.css('div.product-widget')
            unit_price = product_widget.attrib.get('data-unitprice')
            case_price = product_widget.attrib.get('data-caseprice')
            
            result = {
                "store": "chef_store",
                "url": url,
                "name": data.get("name"),
                "price": float(case_price) if case_price else None,
                "price_string": f"${case_price}/Case" if case_price else None,
                "price_per_unit": float(unit_price) if unit_price else None,
                "price_per_unit_string": f"${unit_price}" if unit_price else None,
                "store_id": store_id,
                "store_address": store_address,

                "sku": data.get("sku"),
                "brand": data.get("brand", {}).get("name"),
                "category": data.get("category")
            }
            
            logger.info(f"Successfully extracted product info: {result}")
            return result

        except Exception as e:
            logger.error(f"Error extracting product info: {e}")
            return None