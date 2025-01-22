from parsel import Selector
from .base_scraper import BaseScraper, logger
from typing import Dict
import json

class AlbertsonsScraper(BaseScraper):
    def get_scraper_config(self) -> dict:
        return {
            "untra_premium": True,
            'max_cost': '30',
            "retry_times": 1,
            "country_code": "us",
            "device_type": "desktop",
            "keep_headers": True,
            "headers": {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5"
            }
        }

    async def extract_product_info(self, html: str, url: str) -> Dict:
        try:
            logger.info(f"Starting to extract product info for URL: {url}")
            selector = Selector(text=html)
            
            # Extract product name from meta tags
            name = selector.css('meta[property="og:title"]::attr(content)').get()
            if name:
                name = name.replace("- albertsons", "").strip()
            
            # Find script containing initialPdpResponse
            scripts = selector.css('script::text').getall()
            price = None
            price_per_pound = None
            store_id = None
            
            for script in scripts:
                if 'initialPdpResponse' in script:
                    try:
                        # Find the start of the JSON object
                        start_idx = script.find('initialPdpResponse')
                        if start_idx != -1:
                            # Extract the relevant portion of the JSON
                            json_text = script[start_idx:]
                            json_start = json_text.find('{')
                            if json_start != -1:
                                json_text = json_text[json_start:]
                                # Find matching closing brace
                                brace_count = 1
                                end_idx = -1
                                for j, char in enumerate(json_text[1:], 1):
                                    if char == '{':
                                        brace_count += 1
                                    elif char == '}':
                                        brace_count -= 1
                                        if brace_count == 0:
                                            end_idx = j + 1
                                            break
                                
                                if end_idx != -1:
                                    json_text = json_text[:end_idx]
                                    json_text = json_text.replace('\\"', '"')
                                    data = json.loads(json_text)
                                    catalog_data = data.get('catalog', {}).get('response', {}).get('docs', [{}])[0]
                                    price = catalog_data.get('price')
                                    price_per_pound = catalog_data.get('pricePer')
                                    store_id = catalog_data.get('storeId')
                                    break
                    except json.JSONDecodeError as e:
                        logger.error(f"JSON decode error: {str(e)}")
                        continue
            
            result = {
                "store": "albertsons",
                "store_id": store_id,
                "url": url,
                "name": name,
                "price": float(price) if price else None,
                "price_string": f"${price:.2f}" if price else None,
                "price_per_pound_string": f"${price_per_pound:.2f}" if price_per_pound else None,
                "price_per_pound": float(price_per_pound) if price_per_pound else None
            }
            
            logger.info(f"Successfully extracted product info: {result}")
            return result
        except Exception as e:
            logger.error(f"Error parsing Albertsons product info: {str(e)}")
            return None