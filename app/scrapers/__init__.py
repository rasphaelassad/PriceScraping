"""
Price scraping functionality for various online stores.
"""
from typing import Type, List
import logging
from .base import BaseScraper
from .stores import (
    WalmartScraper,
    CostcoScraper,
    AlbertsonsScraper,
    ChefStoreScraper,
)

logger = logging.getLogger(__name__)

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

def get_scraper_for_store(store_name: str) -> BaseScraper:
    """
    Get appropriate scraper instance for a store name.
    
    Args:
        store_name: Name of the store to get scraper for
        
    Returns:
        Instance of appropriate scraper class
        
    Raises:
        ValueError: If no scraper is found for the store
    """
    logger.info(f"Finding scraper for store: {store_name}")
    
    for scraper_class in AVAILABLE_SCRAPERS:
        if scraper_class.store_name.lower() == store_name.lower():
            logger.info(f"Found matching scraper: {scraper_class.__name__}")
            return scraper_class()
    
    supported = ", ".join(get_supported_stores())
    error_msg = f"No scraper found for store: {store_name}. Supported stores are: {supported}"
    logger.error(error_msg)
    raise ValueError(error_msg)

def get_scraper_for_url(url: str) -> BaseScraper:
    """Get appropriate scraper instance for a URL."""
    logger.info(f"Finding scraper for URL: {url}")
    
    for scraper_class in AVAILABLE_SCRAPERS:
        logger.debug(f"Checking if {scraper_class.__name__} can handle URL")
        try:
            if scraper_class.can_handle_url(url):
                logger.info(f"Found matching scraper: {scraper_class.__name__}")
                return scraper_class()
            else:
                logger.debug(f"{scraper_class.__name__} cannot handle URL")
        except Exception as e:
            logger.error(f"Error checking {scraper_class.__name__}: {str(e)}")
    
    supported = ", ".join(get_supported_stores())
    error_msg = f"No scraper found for URL: {url}. Supported stores are: {supported}"
    logger.error(error_msg)
    raise ValueError(error_msg)

__all__ = [
    'BaseScraper',
    'get_supported_stores',
    'get_scraper_for_store',
    'get_scraper_for_url',
    'WalmartScraper',
    'CostcoScraper',
    'AlbertsonsScraper',
    'ChefStoreScraper',
]
