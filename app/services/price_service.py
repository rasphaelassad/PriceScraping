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
        """Initialize the service."""
        self.scraper_factory = ScraperFactory()
        self._background_tasks: Set[asyncio.Task] = set()

    def _task_done_callback(self, task):
        """Remove task from set when done."""
        try:
            self._background_tasks.remove(task)
        except KeyError:
            pass

    async def get_prices(self, request: PriceRequest) -> Dict[str, Any]:
        """
        Get prices for multiple URLs, automatically identifying stores.
        
        Args:
            request: The price request containing URLs to process.
            
        Returns:
            Dict mapping URLs to their results.
        """
        try:
            # Group URLs by store
            store_urls: Dict[str, list] = {}
            unknown_urls: list = []
            
            for url in request.urls:
                store = self.scraper_factory.identify_store_from_url(str(url))
                if store:
                    if store not in store_urls:
                        store_urls[store] = []
                    store_urls[store].append(str(url))
                else:
                    unknown_urls.append(str(url))

            if unknown_urls:
                logger.warning(f"Found {len(unknown_urls)} URLs with unknown stores: {unknown_urls}")
                supported = ", ".join(self.scraper_factory.get_supported_stores())
                raise HTTPException(
                    status_code=400,
                    detail=f"Some URLs are from unsupported stores. Supported stores are: {supported}"
                )

            # Process each store's URLs concurrently
            tasks = []
            for store_name, urls in store_urls.items():
                scraper = self.scraper_factory.get_scraper(store_name)
                for url in urls:
                    tasks.append(self._process_url(scraper, url))

            # Wait for all tasks to complete
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Combine results
            combined_results = {}
            for url, result in zip([str(u) for u in request.urls], results):
                if isinstance(result, Exception):
                    combined_results[url] = {
                        "request_status": {
                            "status": "failed",
                            "job_id": None,
                            "start_time": datetime.now(timezone.utc),
                            "elapsed_time_seconds": 0.0,
                            "error_message": str(result)
                        }
                    }
                else:
                    combined_results[url] = result

            return combined_results

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error processing price request: {e}")
            logger.error(traceback.format_exc())
            raise HTTPException(status_code=500, detail=str(e))

    async def _process_url(self, scraper, url: str) -> Dict[str, Any]:
        """Process a single URL with its scraper."""
        try:
            return await scraper.get_price(url)
        except Exception as e:
            logger.error(f"Error processing URL {url}: {e}")
            return {
                "request_status": {
                    "status": "failed",
                    "job_id": None,
                    "start_time": datetime.now(timezone.utc),
                    "elapsed_time_seconds": 0.0,
                    "error_message": str(e)
                }
            }

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