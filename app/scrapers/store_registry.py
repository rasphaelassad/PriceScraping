
from .walmart_scraper import WalmartScraper
from .costco_scraper import CostcoScraper
from .chefstore_scraper import ChefStoreScraper
from .albertsons_scraper import AlbertsonsScraper

SUPPORTED_STORES = {
    "walmart": WalmartScraper,
    "costco": CostcoScraper,
    "chefstore": ChefStoreScraper,
    "albertsons": AlbertsonsScraper
}
