from typing import Dict, Set, List, Any, Optional
from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.core.scraper_factory import ScraperFactory
from app.core.cache_manager import CacheManager
from app.schemas.request_schemas import PriceRequest, UrlResult, ProductInfo, RequestStatus
from app.core.config import get_settings
from app.models.database import get_async_db
import logging
import asyncio
import traceback
from datetime import datetime, timezone
import weakref

logger = logging.getLogger(__name__)

class PriceService:
    """Service for handling price-related operations."""
    
    def __init__(self):
        """Initialize the service with scraper factory."""
        self.scraper_factory = ScraperFactory()
        self._background_tasks: Set[asyncio.Task] = set()

    def _task_done_callback(self, task):
        """Remove task from set when done."""
        try:
            self._background_tasks.remove(task)
        except KeyError:
            pass

    async def get_prices(self, request: PriceRequest) -> Dict[str, Any]:
        """Get prices for the requested URLs."""
        async with get_async_db() as db:
            try:
                cache_manager = CacheManager(db)
                
                # Get scraper for the store
                scraper = self.scraper_factory.get_scraper(request.store_name)
                if not scraper:
                    raise HTTPException(status_code=400, detail=f"Invalid store: {request.store_name}")
                
                # Process each URL
                results = {}
                for url in request.urls:
                    # Check cache first using original URL
                    cached_result = await cache_manager.get_cached_product(str(url), request.store_name)
                    if cached_result:
                        # Format cached result to match expected structure
                        results[str(url)] = {
                            "request_status": {
                                "status": "completed",
                                "job_id": cached_result.get("id"),  # Use database ID as job ID
                                "start_time": cached_result.get("timestamp"),
                                "elapsed_time_seconds": 0.0,  # Already completed, so no elapsed time
                                "price_found": True,
                                "details": "Retrieved from cache"
                            },
                            "result": {
                                "store": cached_result.get("store"),
                                "url": cached_result.get("url"),
                                "name": cached_result.get("name"),
                                "price": cached_result.get("price"),
                                "price_string": cached_result.get("price_string"),
                                "price_per_unit": cached_result.get("price_per_unit"),
                                "price_per_unit_string": cached_result.get("price_per_unit_string"),
                                "store_id": cached_result.get("store_id"),
                                "store_address": cached_result.get("store_address"),
                                "store_zip": cached_result.get("store_zip"),
                                "brand": cached_result.get("brand"),
                                "sku": cached_result.get("sku"),
                                "category": cached_result.get("category"),
                                "timestamp": cached_result.get("timestamp")
                            }
                        }
                        continue
                        
                    # If not in cache, add to URLs to scrape
                    if str(url) not in results:
                        results[str(url)] = await scraper.get_price(str(url))
                        
                return results
                
            except Exception as e:
                logger.error(f"Error in get_prices: {e}")
                raise HTTPException(status_code=400, detail=str(e))

    async def _process_urls_background(self, store_name: str, urls: List[str]):
        """Process URLs in the background."""
        async with get_async_db() as db:
            try:
                cache_manager = CacheManager(db)
                scraper = self.scraper_factory.get_scraper(store_name)
                results = await scraper.get_prices(urls)
                
                for url in urls:
                    try:
                        if url in results:
                            # Update cache with successful result
                            await cache_manager.update_cache_with_result(
                                url, 
                                store_name, 
                                results[url]["result"],
                                results[url]["request_status"]["job_id"]
                            )
                        else:
                            # Update cache with error if URL not in results
                            error_msg = "URL not found in scraper results"
                            await cache_manager.update_cache_with_error(url, store_name, error_msg)
                    except Exception as e:
                        logger.error(f"Error updating cache for {url}: {e}")
                        await cache_manager.update_cache_with_error(url, store_name, str(e))
                    
            except Exception as e:
                logger.error(f"Error in background processing: {e}")
                logger.error(traceback.format_exc())
                # Update cache with error for all URLs
                for url in urls:
                    try:
                        await cache_manager.update_cache_with_error(url, store_name, str(e))
                    except Exception as cache_error:
                        logger.error(f"Error updating cache with error for {url}: {cache_error}")

    async def get_raw_content(self, request: PriceRequest) -> Dict[str, Any]:
        """Get raw HTML content for the requested URLs."""
        async with get_async_db() as db:
            try:
                scraper = self.scraper_factory.get_scraper(request.store_name)
                if not scraper:
                    raise HTTPException(status_code=400, detail=f"Invalid store: {request.store_name}")
                    
                return await scraper.get_raw_content(request.urls)
                
            except Exception as e:
                logger.error(f"Error getting raw content: {e}")
                raise HTTPException(status_code=400, detail=str(e))

    async def cleanup(self):
        """Clean up any running background tasks."""
        for task in self._background_tasks:
            if not task.done():
                task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass 