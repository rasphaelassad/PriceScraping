from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
from typing import Dict, List
import logging
import asyncio

from app.schemas.request_schemas import PriceRequest, PriceResponse, ProductInfo, RequestStatus, UrlResult
from app.models.database import Product, PendingRequest
from app.scrapers.costco_scraper import CostcoScraper
from app.scrapers.walmart_scraper import WalmartScraper
from app.scrapers.albertsons_scraper import AlbertsonsScraper
from app.scrapers.chefstore_scraper import ChefStoreScraper
from app.services.cache_service import CacheService
from app.core.logging_config import get_logger

logger = get_logger(__name__)

class PriceService:
    SUPPORTED_STORES = {
        "walmart": WalmartScraper,
        "albertsons": AlbertsonsScraper,
        "chefstore": ChefStoreScraper,
        "costco": CostcoScraper,
    }

    def __init__(self, db: Session, cache_service: CacheService):
        self.db = db
        self.cache_service = cache_service

    @staticmethod
    def get_supported_stores():
        return {"supported_stores": list(PriceService.SUPPORTED_STORES.keys())}

    async def get_prices(self, request: PriceRequest) -> PriceResponse:
        """Get prices for the requested URLs"""
        if request.store not in self.SUPPORTED_STORES:
            raise ValueError(f"Unsupported store: {request.store}")

        logger.info(f"Processing {len(request.urls)} URLs for store: {request.store}")
        
        # Get cached results
        cached_results = self.cache_service.get_cached_results(request.urls)
        urls_to_fetch = [url for url in request.urls if str(url) not in cached_results]

        if not urls_to_fetch:
            logger.info("All results found in cache")
            return PriceResponse(
                results={url: UrlResult(status=RequestStatus.SUCCESS, product=product)
                        for url, product in cached_results.items()}
            )

        # Check for pending requests
        pending = self.cache_service.get_pending_requests(request.store, urls_to_fetch)
        urls_to_fetch = [url for url in urls_to_fetch if str(url) not in pending]

        # Add new requests to pending
        self.cache_service.add_pending_requests(request.store, urls_to_fetch)

        try:
            # Initialize scraper
            scraper = self.SUPPORTED_STORES[request.store]()
            
            # Fetch prices
            results = {}
            for url in request.urls:
                url_str = str(url)
                if url_str in cached_results:
                    results[url_str] = UrlResult(
                        status=RequestStatus.SUCCESS,
                        product=cached_results[url_str]
                    )
                elif url_str in pending:
                    results[url_str] = UrlResult(
                        status=RequestStatus.PENDING
                    )
                else:
                    try:
                        product = await scraper.get_prices(url_str)
                        results[url_str] = UrlResult(
                            status=RequestStatus.SUCCESS,
                            product=product
                        )
                    except Exception as e:
                        logger.error(f"Error scraping URL {url_str}: {str(e)}", exc_info=True)
                        results[url_str] = UrlResult(
                            status=RequestStatus.ERROR,
                            error=str(e)
                        )

            # Cache successful results
            self.cache_service.cache_results(results)
            
            # Remove completed requests from pending
            self.cache_service.remove_pending_requests(urls_to_fetch)

            return PriceResponse(results=results)

        except Exception as e:
            logger.error(f"Error in get_prices: {str(e)}", exc_info=True)
            self.cache_service.remove_pending_requests(urls_to_fetch)
            raise

    async def get_raw_html(self, request: PriceRequest) -> Dict[str, str]:
        """Get raw HTML/JSON response without processing"""
        if request.store not in self.SUPPORTED_STORES:
            raise ValueError(f"Unsupported store: {request.store}")

        scraper = self.SUPPORTED_STORES[request.store]()
        raw_responses = {}

        for url in request.urls:
            try:
                raw_response = await scraper.get_raw_response(str(url))
                raw_responses[str(url)] = raw_response
            except Exception as e:
                logger.error(f"Error getting raw response for {url}: {str(e)}", exc_info=True)
                raw_responses[str(url)] = {"error": str(e)}

        return raw_responses
