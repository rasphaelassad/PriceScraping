from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from app.models.database import Product, RequestCache, get_db
from app.schemas.request_schemas import ProductInfo, RequestStatus
from app.core.config import get_settings
from typing import Optional, Tuple, Union
import logging
import time
import traceback

logger = logging.getLogger(__name__)

class CacheManager:
    def __init__(self):
        self.settings = get_settings()

    def get_cached_product(self, url: str, store: str) -> Tuple[Optional[ProductInfo], Optional[RequestStatus]]:
        """Get cached product and its status if available."""
        logger.info(f"Attempting to get cached product for URL: {url}, Store: {store}")
        try:
            with get_db() as db:
                try:
                    logger.debug("Querying request cache...")
                    cache_entry = (
                        db.query(RequestCache)
                        .filter(RequestCache.url == str(url))
                        .filter(RequestCache.store == store)
                        .order_by(RequestCache.update_time.desc())
                        .first()
                    )

                    if not cache_entry:
                        logger.debug(f"No cache entry found for {url}")
                        return None, None

                    logger.debug(f"Found cache entry: status={cache_entry.status}, job_id={cache_entry.job_id}")

                    # Ensure all times are timezone-aware
                    now = datetime.now(timezone.utc)
                    start_time = cache_entry.start_time
                    if start_time.tzinfo is None:
                        start_time = start_time.replace(tzinfo=timezone.utc)
                        logger.debug("Converted start_time to UTC")
                    update_time = cache_entry.update_time
                    if update_time.tzinfo is None:
                        update_time = update_time.replace(tzinfo=timezone.utc)
                        logger.debug("Converted update_time to UTC")

                    # Calculate elapsed time
                    elapsed_time = (now - start_time).total_seconds()
                    logger.debug(f"Elapsed time: {elapsed_time:.2f} seconds")

                    # Check if entry is stale
                    is_stale = (now - update_time).total_seconds() > (self.settings.cache_ttl_hours * 3600)
                    logger.debug(f"Cache entry stale status: {is_stale}")

                    # Create status response
                    status = RequestStatus(
                        status=cache_entry.status,
                        job_id=cache_entry.job_id,
                        start_time=start_time,
                        elapsed_time_seconds=elapsed_time,
                        remaining_time_seconds=max(0, self.settings.request_timeout_minutes * 60 - elapsed_time),
                        price_found=cache_entry.price_found,
                        error_message=cache_entry.error_message,
                        details=self._get_status_details(cache_entry.status, elapsed_time)
                    )
                    logger.debug(f"Created status response: {status.model_dump()}")

                    # Return cached product if available and not stale
                    if cache_entry.status == 'completed' and not is_stale:
                        logger.debug("Cache entry is valid and not stale, attempting to get product...")
                        product = self._get_product_from_cache(db, url, store)
                        if product:
                            logger.debug("Successfully retrieved product from cache")
                            db.commit()  # Commit the transaction if successful
                            return product, status
                        else:
                            logger.debug("No product found in cache despite completed status")

                    logger.debug("Committing transaction with no product")
                    db.commit()  # Commit even if no product found
                    return None, status

                except Exception as e:
                    logger.error(f"Error in database transaction: {e}")
                    logger.error(f"Transaction traceback: {traceback.format_exc()}")
                    db.rollback()
                    raise

        except Exception as e:
            logger.error(f"Error getting cached product: {e}")
            logger.error(f"Full traceback: {traceback.format_exc()}")
            return None, None

    def _get_product_from_cache(self, db: Session, url: str, store: str) -> Optional[ProductInfo]:
        """Get product from cache if available."""
        logger.info(f"Attempting to get product from cache - URL: {url}, Store: {store}")
        try:
            logger.debug("Querying products table...")
            product = (
                db.query(Product)
                .filter(Product.url == str(url))
                .filter(Product.store == store)
                .order_by(Product.timestamp.desc())
                .first()
            )
            
            if not product:
                logger.debug(f"No product found in cache for {url}")
                return None
                
            logger.debug(f"Found product in cache: ID={product.id}, Name={product.name}, Price={product.price}")
            try:
                logger.debug("Converting product to ProductInfo...")
                result = product.to_product_info()
                logger.debug(f"Successfully converted product to ProductInfo: {result.model_dump()}")
                return result
            except Exception as conversion_error:
                logger.error(f"Error converting product to ProductInfo - Error: {str(conversion_error)}")
                logger.error(f"Product data: {product.__dict__}")
                logger.error(f"Conversion traceback: {traceback.format_exc()}")
                raise
                
        except Exception as e:
            logger.error(f"Error getting product from cache - Error: {str(e)}")
            logger.error(f"Query traceback: {traceback.format_exc()}")
            raise  # Let the parent handle the rollback

    def create_pending_request(self, url: str, store: str) -> RequestStatus:
        """Create a new pending request and return its status."""
        now = datetime.now(timezone.utc)
        job_id = f"{store}_{int(now.timestamp())}_{url[-8:]}"

        # Create and save new cache entry
        cache_entry = RequestCache(
            store=store,
            url=str(url),
            job_id=job_id,
            status='pending',
            start_time=now,
            update_time=now,
            price_found=False,
            error_message=None
        )
        
        try:
            with get_db() as db:
                db.add(cache_entry)
                db.commit()
        except Exception as e:
            logger.error(f"Error creating cache entry: {e}")
            with get_db() as db:
                db.rollback()
            raise

        # Return initial status
        return RequestStatus(
            status='running',
            job_id=job_id,
            start_time=now,
            elapsed_time_seconds=0,
            remaining_time_seconds=self.settings.request_timeout_minutes * 60,
            price_found=None,
            error_message=None,
            details="Request just started"
        )

    def update_request_status(self, url: str, store: str, status: str, error_message: Optional[str] = None):
        """Update the status of a request."""
        logger.info(f"Updating request status - URL: {url}, Store: {store}, Status: {status}")
        try:
            with get_db() as db:
                try:
                    logger.debug("Querying request cache for status update...")
                    cache_entry = (
                        db.query(RequestCache)
                        .filter(RequestCache.url == str(url))
                        .filter(RequestCache.store == store)
                        .order_by(RequestCache.update_time.desc())
                        .first()
                    )

                    if cache_entry:
                        logger.debug(f"Updating cache entry - Previous status: {cache_entry.status}")
                        cache_entry.status = status
                        cache_entry.update_time = datetime.now(timezone.utc)
                        if error_message:
                            logger.debug(f"Setting error message: {error_message}")
                            cache_entry.error_message = error_message
                        cache_entry.price_found = (status == 'completed')
                        
                        logger.debug("Committing status update...")
                        db.commit()
                        logger.info(f"Successfully updated request status for {url} to {status}")
                    else:
                        logger.warning(f"No cache entry found for {url} in store {store}")
                        
                except Exception as e:
                    logger.error(f"Error in database transaction: {str(e)}")
                    logger.error(f"Transaction traceback: {traceback.format_exc()}")
                    db.rollback()
                    raise
                    
        except Exception as e:
            logger.error(f"Error updating request status: {str(e)}")
            logger.error(f"Full traceback: {traceback.format_exc()}")
            raise

    def cache_product(self, product_info: ProductInfo):
        """Cache a product in the database."""
        logger.info(f"Attempting to cache product - URL: {product_info.url}, Store: {product_info.store}")
        try:
            url_str = str(product_info.url)
            with get_db() as db:
                try:
                    logger.debug("Checking for existing product...")
                    existing = (
                        db.query(Product)
                        .filter(Product.url == url_str)
                        .filter(Product.store == product_info.store)
                        .first()
                    )

                    if existing:
                        logger.debug(f"Updating existing product - ID: {existing.id}")
                        product_data = product_info.model_dump()
                        logger.debug(f"Update data: {product_data}")
                        for key, value in product_data.items():
                            setattr(existing, key, value)
                    else:
                        logger.debug("Creating new product entry")
                        db_product = Product.from_product_info(product_info)
                        db.add(db_product)

                    logger.debug("Committing product changes...")
                    db.commit()
                    
                    logger.debug("Updating request status...")
                    self.update_request_status(url_str, product_info.store, 'completed')
                    logger.info("Successfully cached product and updated status")
                except Exception as e:
                    logger.error(f"Error in database transaction: {str(e)}")
                    logger.error(f"Transaction traceback: {traceback.format_exc()}")
                    db.rollback()
                    raise

        except Exception as e:
            logger.error(f"Error caching product {product_info.url}: {str(e)}")
            logger.error(f"Full traceback: {traceback.format_exc()}")
            try:
                logger.debug("Attempting to update request status to failed...")
                self.update_request_status(str(product_info.url), product_info.store, 'failed', str(e))
            except Exception as status_error:
                logger.error(f"Failed to update request status after error: {str(status_error)}")
                logger.error(f"Status update traceback: {traceback.format_exc()}")

    def cleanup_stale_entries(self):
        """Clean up stale cache entries."""
        try:
            with get_db() as db:
                cleanup_time = datetime.now(timezone.utc) - timedelta(hours=self.settings.cache_ttl_hours)
                db.query(RequestCache).filter(RequestCache.update_time < cleanup_time).delete()
                db.commit()
        except Exception as e:
            logger.error(f"Error cleaning up stale entries: {e}")
            with get_db() as db:
                db.rollback()
            raise

    def _get_status_details(self, status: str, elapsed_time: float) -> str:
        """Get human-readable status details."""
        if status == 'completed':
            return f"Request completed in {elapsed_time:.1f} seconds"
        elif status == 'pending':
            remaining = max(0, self.settings.request_timeout_minutes * 60 - elapsed_time)
            return f"Request running for {elapsed_time:.1f} seconds, {remaining:.1f} seconds remaining"
        elif status in ['failed', 'timeout']:
            return f"Request {status} after {elapsed_time:.1f} seconds"
        return f"Unknown status: {status}" 