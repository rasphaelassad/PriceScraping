"""
Web scraper implementations for different stores
"""
from typing import Type, List
from .base import BaseScraper
from .walmart import WalmartScraper
from .costco import CostcoScraper
from .albertsons import AlbertsonsScraper
from .chefstore import ChefStoreScraper

# List of available scrapers
AVAILABLE_SCRAPERS: List[Type[BaseScraper]] = [
    WalmartScraper,
    CostcoScraper,
    AlbertsonsScraper,
    ChefStoreScraper,
]

def get_supported_stores() -> list[str]:
    """Get a list of supported store names."""
    return sorted(scraper.store_name for scraper in AVAILABLE_SCRAPERS)

def get_scraper_for_url(url: str) -> BaseScraper:
    """Get appropriate scraper instance for a URL."""
    scraper_class = BaseScraper.get_scraper_for_url(url, AVAILABLE_SCRAPERS)
    if not scraper_class:
        supported = ", ".join(get_supported_stores())
        raise ValueError(f"No scraper found for URL: {url}. Supported stores are: {supported}")
    return scraper_class()
