from typing import Dict
from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.core.scraper_factory import ScraperFactory
from app.core.cache_manager import CacheManager
from app.schemas.request_schemas import PriceRequest, UrlResult, ProductInfo, RequestStatus
from app.core.config import get_settings
import logging
import asyncio
import traceback
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class PriceService:
    def __init__(self, db: Session = None):
        """Initialize service with optional db session (for future use if needed)."""
        self.cache_manager = CacheManager()
        self.settings = get_settings()

    async def get_prices(self, request: PriceRequest) -> Dict[str, UrlResult]:
        """Get prices for the requested URLs."""
        try:
            store_name = request.store_name.lower()
            urls = request.urls
            final_results = {}

            logger.debug(f"Processing request for store: {store_name}, urls: {urls}")

            try:
                # Get scraper instance
                scraper = ScraperFactory.get_scraper(store_name)
                logger.debug(f"Created scraper instance: {scraper.__class__.__name__}")
            except ValueError as e:
                logger.error(f"Invalid store name: {store_name}")
                raise HTTPException(status_code=400, detail=str(e))

            # Clean up stale cache entries
            try:
                self.cache_manager.cleanup_stale_entries()
            except Exception as e:
                logger.error(f"Error cleaning up stale entries: {e}")
                # Continue processing even if cleanup fails

            # Process each URL
            for url in urls:
                url_str = str(url)
                try:
                    # Check cache first
                    product_info, status = self.cache_manager.get_cached_product(url_str, store_name)
                    logger.debug(f"Cache check for {url_str}: product_info={bool(product_info)}, status={status.status if status else None}")

                    if product_info:
                        final_results[url_str] = UrlResult(result=product_info, request_status=status)
                        continue

                    # If we got a status but no product, use that status
                    if status:
                        final_results[url_str] = UrlResult(result=None, request_status=status)
                        continue

                    # Create new request status
                    now = datetime.now(timezone.utc)
                    status = RequestStatus(
                        status="running",
                        job_id=f"{store_name}_{url_str[-8:]}",
                        start_time=now,
                        elapsed_time_seconds=0,
                        remaining_time_seconds=self.settings.request_timeout_minutes * 60,
                        price_found=None,
                        error_message=None,
                        details="Request starting"
                    )

                    # Add to final results
                    final_results[url_str] = UrlResult(result=None, request_status=status)

                    # Create pending request
                    status = self.cache_manager.create_pending_request(url_str, store_name)
                    final_results[url_str].request_status = status

                except Exception as e:
                    logger.error(f"Error processing URL {url_str}: {e}")
                    logger.error(traceback.format_exc())
                    now = datetime.now(timezone.utc)
                    status = RequestStatus(
                        status="failed",
                        job_id=None,
                        start_time=now,
                        elapsed_time_seconds=0,
                        remaining_time_seconds=0,
                        price_found=False,
                        error_message=str(e),
                        details="Error during request setup"
                    )
                    final_results[url_str] = UrlResult(result=None, request_status=status)

            # Start background processing
            if any(result.request_status.status == "running" for result in final_results.values()):
                asyncio.create_task(self._process_urls_background(
                    store_name,
                    [url for url, result in final_results.items() if result.request_status.status == "running"]
                ))

            return final_results

        except Exception as e:
            logger.error(f"Error in get_prices: {e}")
            logger.error(traceback.format_exc())
            raise HTTPException(status_code=500, detail=str(e))

    async def _process_urls_background(self, store_name: str, urls: list[str]):
        """Process URLs in the background."""
        try:
            logger.info(f"Starting background processing for URLs: {urls}")
            scraper = ScraperFactory.get_scraper(store_name)

            try:
                # Set timeout for the scraping
                async with asyncio.timeout(self.settings.request_timeout_minutes * 60):
                    try:
                        results = await scraper.get_prices(urls)
                        logger.debug(f"Got scraper results: {results}")

                        # Cache results
                        for url in urls:
                            url_str = str(url)
                            price_info = results.get(url_str)
                            if price_info:
                                price_info['store'] = store_name
                                price_info['url'] = url_str
                                self.cache_manager.cache_product(ProductInfo(**price_info))
                            else:
                                self.cache_manager.update_request_status(
                                    url_str, 
                                    store_name, 
                                    'completed', 
                                    "Price not found"
                                )
                    except Exception as e:
                        logger.error(f"Error in scraper.get_prices: {e}")
                        logger.error(traceback.format_exc())
                        for url in urls:
                            self.cache_manager.update_request_status(
                                str(url),
                                store_name,
                                'failed',
                                str(e)
                            )

            except asyncio.TimeoutError:
                logger.error("Background processing timed out")
                for url in urls:
                    self.cache_manager.update_request_status(
                        str(url),
                        store_name,
                        'timeout',
                        "Request timed out"
                    )

            except Exception as e:
                logger.error(f"Error in background processing: {e}")
                logger.error(traceback.format_exc())
                for url in urls:
                    self.cache_manager.update_request_status(
                        str(url),
                        store_name,
                        'failed',
                        str(e)
                    )

        except Exception as e:
            logger.error(f"Background task error: {e}")
            logger.error(traceback.format_exc())

    async def get_raw_content(self, request: PriceRequest) -> Dict:
        """Get raw HTML/JSON content for the requested URLs."""
        try:
            scraper = ScraperFactory.get_scraper(request.store_name)
            return await scraper.get_raw_content(request.urls)
        except ValueError as e:
            logger.error(f"Invalid store name: {request.store_name}")
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.error(f"Error getting raw content: {e}")
            logger.error(traceback.format_exc())
            raise HTTPException(status_code=500, detail=str(e)) 