import os
import sys
import pytest
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.scrapers.walmart_scraper import WalmartScraper
from app.scrapers.albertsons_scraper import AlbertsonsScraper

@pytest.mark.asyncio
async def test_walmart_scraper():
    walmart_scraper = WalmartScraper()
    
    walmart_urls = [
    "https://www.walmart.com/ip/21553590/",
    "https://www.walmart.com/ip/319841736/"
]
    
    prices = await walmart_scraper.get_prices(walmart_urls)
    
    print(f"Walmart Prices: {prices}")  # Helpful for debugging
    assert prices is not None
    assert all(price is not None for price in prices.values())

@pytest.mark.asyncio
async def test_albertsons_scraper():
    albertsons_scraper = AlbertsonsScraper()
    albertsons_urls = [
        "https://www.albertsons.com/product1",
        # Add more test URLs if needed
    ]
    
    prices = await albertsons_scraper.get_prices(albertsons_urls)
    print(f"Albertsons Prices: {prices}")  # Helpful for debugging
    assert prices is not None 

if __name__ == "__main__":
    import asyncio
    
    # Choose which test to run
    asyncio.run(test_walmart_scraper())
    # asyncio.run(test_albertsons_scraper()) 