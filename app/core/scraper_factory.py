from typing import Type, Dict
from app.scrapers.base_scraper import BaseScraper
from app.scrapers.costco_scraper import CostcoScraper
from app.scrapers.walmart_scraper import WalmartScraper
from app.scrapers.albertsons_scraper import AlbertsonsScraper
from app.scrapers.chefstore_scraper import ChefStoreScraper

class ScraperFactory:
    _scrapers: Dict[str, Type[BaseScraper]] = {
        "walmart": WalmartScraper,
        "albertsons": AlbertsonsScraper,
        "chefstore": ChefStoreScraper,
        "costco": CostcoScraper,
    }

    @classmethod
    def get_scraper(cls, store_name: str) -> BaseScraper:
        """Get a scraper instance for the given store."""
        scraper_class = cls._scrapers.get(store_name.lower())
        if not scraper_class:
            raise ValueError(f"Unsupported store: {store_name}")
        return scraper_class()

    @classmethod
    def get_supported_stores(cls) -> list[str]:
        """Get a list of supported store names."""
        return list(cls._scrapers.keys()) 