from typing import Type, Dict, Optional
from app.scrapers.base_scraper import BaseScraper
from app.scrapers.costco_scraper import CostcoScraper
from app.scrapers.walmart_scraper import WalmartScraper
from app.scrapers.albertsons_scraper import AlbertsonsScraper
from app.scrapers.chefstore_scraper import ChefStoreScraper
import logging

logger = logging.getLogger(__name__)

class ScraperFactory:
    """Factory class for creating store-specific scrapers."""
    
    _scrapers: Dict[str, Type[BaseScraper]] = {
        "walmart": WalmartScraper,
        "albertsons": AlbertsonsScraper,
        "chefstore": ChefStoreScraper,
        "costco": CostcoScraper,
    }

    @classmethod
    def get_scraper(cls, store_name: str) -> BaseScraper:
        """
        Get a scraper instance for the given store.
        
        Args:
            store_name: The name of the store to get a scraper for.
            
        Returns:
            An instance of the appropriate scraper for the store.
            
        Raises:
            ValueError: If the store is not supported.
        """
        if not store_name:
            logger.error("Store name cannot be empty")
            raise ValueError("Store name cannot be empty")
            
        normalized_name = store_name.lower().strip()
        logger.debug(f"Getting scraper for store: {normalized_name}")
        
        scraper_class = cls._scrapers.get(normalized_name)
        if not scraper_class:
            supported = ", ".join(sorted(cls._scrapers.keys()))
            error_msg = f"Unsupported store: {store_name}. Supported stores are: {supported}"
            logger.error(error_msg)
            raise ValueError(error_msg)
            
        try:
            scraper = scraper_class()
            logger.info(f"Created scraper instance: {scraper.__class__.__name__}")
            return scraper
        except Exception as e:
            error_msg = f"Failed to create scraper for {store_name}: {str(e)}"
            logger.error(error_msg)
            raise ValueError(error_msg)

    @classmethod
    def get_supported_stores(cls) -> list[str]:
        """Get a list of supported store names."""
        return sorted(cls._scrapers.keys())

    @classmethod
    def register_scraper(cls, store_name: str, scraper_class: Type[BaseScraper]) -> None:
        """
        Register a new scraper class for a store.
        
        Args:
            store_name: The name of the store to register the scraper for.
            scraper_class: The scraper class to register.
            
        Raises:
            ValueError: If the store name is invalid or the scraper class is not a subclass of BaseScraper.
        """
        if not store_name:
            logger.error("Store name cannot be empty")
            raise ValueError("Store name cannot be empty")
            
        if not issubclass(scraper_class, BaseScraper):
            error_msg = f"Scraper class must be a subclass of BaseScraper, got {scraper_class}"
            logger.error(error_msg)
            raise ValueError(error_msg)
            
        normalized_name = store_name.lower().strip()
        cls._scrapers[normalized_name] = scraper_class
        logger.info(f"Registered scraper {scraper_class.__name__} for store {normalized_name}")

    @classmethod
    def unregister_scraper(cls, store_name: str) -> None:
        """
        Unregister a scraper for a store.
        
        Args:
            store_name: The name of the store to unregister the scraper for.
            
        Raises:
            ValueError: If the store is not registered.
        """
        if not store_name:
            logger.error("Store name cannot be empty")
            raise ValueError("Store name cannot be empty")
            
        normalized_name = store_name.lower().strip()
        if normalized_name not in cls._scrapers:
            error_msg = f"No scraper registered for store: {store_name}"
            logger.error(error_msg)
            raise ValueError(error_msg)
            
        del cls._scrapers[normalized_name]
        logger.info(f"Unregistered scraper for store {normalized_name}")

    @classmethod
    def get_scraper_class(cls, store_name: str) -> Optional[Type[BaseScraper]]:
        """
        Get the scraper class for a store without instantiating it.
        
        Args:
            store_name: The name of the store to get the scraper class for.
            
        Returns:
            The scraper class if found, None otherwise.
        """
        if not store_name:
            return None
            
        normalized_name = store_name.lower().strip()
        return cls._scrapers.get(normalized_name) 