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
SCRAPERS: List[Type[BaseScraper]] = [
    WalmartScraper,
    CostcoScraper,
    AlbertsonsScraper,
    ChefStoreScraper,
]

def get_supported_stores() -> List[str]:
    """Get a list of supported store names."""
    return sorted(scraper.store_name for scraper in SCRAPERS)

def get_scraper_for_url(url: str) -> BaseScraper:
    """Get appropriate scraper instance for a URL."""
    for scraper_class in SCRAPERS:
        if scraper_class.can_handle_url(url):
            return scraper_class()
    supported = ", ".join(get_supported_stores())
    raise ValueError(f"No scraper found for URL: {url}. Supported stores are: {supported}")

__all__ = [
    'BaseScraper',
    'get_supported_stores',
    'get_scraper_for_url',
    'WalmartScraper',
    'CostcoScraper',
    'AlbertsonsScraper',
    'ChefStoreScraper',
]
