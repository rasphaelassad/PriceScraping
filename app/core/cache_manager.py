from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from app.models.database import Product, RequestCache, get_db
from app.schemas.request_schemas import ProductInfo, RequestStatus
from app.core.config import get_settings
from typing import Optional, Tuple, Union, Dict, Any, List
import logging
import time
import traceback
from sqlalchemy.exc import IntegrityError
import re

logger = logging.getLogger(__name__)

class CacheManager:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()
        self.CACHE_DURATION = timedelta(hours=24)
        self.logger = logging.getLogger(__name__)

    async def get_cached_product(self, url: str, store_name: str) -> Optional[Dict[str, Any]]:
        """Get cached product information if available."""
        self.logger.info(f"Attempting to get cached product for URL: {url}, Store: {store_name}")
        
        try:
            # Check request cache first
            cache_entry = (
                self.db.query(RequestCache)
                .filter(RequestCache.url == url)
                .filter(RequestCache.store == store_name)
                .order_by(RequestCache.update_time.desc())
                .first()
            )

            if cache_entry:
                self.logger.info(f"Found cache entry for URL: {url}")
                if cache_entry.status in ["pending", "running"]:
                    return None

            # Then check products table
            self.logger.info(f"Attempting to get product from cache - URL: {url}, Store: {store_name}")
            product = (
                self.db.query(Product)
                .filter(Product.url == url)
                .filter(Product.store == store_name)
                .order_by(Product.timestamp.desc())
                .first()
            )

            if product:
                self.logger.info(f"Found cached product for URL: {url}")
                return product.__dict__
            else:
                self.logger.info(f"No cached product found for URL: {url}")
                return None

        except Exception as e:
            self.logger.error(f"Error getting cached product: {e}")
            return None

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

        # First try to get existing request
        with get_db() as db:
            existing_request = self._get_latest_request(str(url), store, db)
            if existing_request and existing_request.status in ['pending', 'running']:
                # Ensure start_time is timezone-aware
                start_time = existing_request.start_time
                if start_time.tzinfo is None:
                    start_time = start_time.replace(tzinfo=timezone.utc)
                
                # Return existing request status
                elapsed_time = (now - start_time).total_seconds()
                return RequestStatus(
                    status=existing_request.status,
                    job_id=existing_request.job_id,
                    start_time=start_time,
                    elapsed_time_seconds=elapsed_time,
                    remaining_time_seconds=max(0, self.settings.request_timeout_minutes * 60 - elapsed_time),
                    price_found=existing_request.price_found,
                    error_message=existing_request.error_message,
                    details="Using existing request"
                )

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
                db.add(cache_entry)
                db.commit()
            except IntegrityError:
                # If we hit a unique constraint violation, get the existing request
                db.rollback()
                existing_request = self._get_latest_request(str(url), store, db)
                if existing_request:
                    # Ensure start_time is timezone-aware
                    start_time = existing_request.start_time
                    if start_time.tzinfo is None:
                        start_time = start_time.replace(tzinfo=timezone.utc)
                    
                    elapsed_time = (now - start_time).total_seconds()
                    return RequestStatus(
                        status=existing_request.status,
                        job_id=existing_request.job_id,
                        start_time=start_time,
                        elapsed_time_seconds=elapsed_time,
                        remaining_time_seconds=max(0, self.settings.request_timeout_minutes * 60 - elapsed_time),
                        price_found=existing_request.price_found,
                        error_message=existing_request.error_message,
                        details="Using existing request after conflict"
                    )
                else:
                    # This should never happen, but just in case
                    logger.error("Failed to find existing request after IntegrityError")
                    raise

            # Return initial status
            return RequestStatus(
                status='pending',
                job_id=job_id,
                start_time=now,
                elapsed_time_seconds=0,
                remaining_time_seconds=self.settings.request_timeout_minutes * 60,
                price_found=None,
                error_message=None,
                details="Request created"
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

    def cleanup_stale_entries(self) -> None:
        """Remove stale entries from the cache."""
        try:
            with get_db() as db:
                timeout = datetime.now(timezone.utc) - timedelta(minutes=self.settings.request_timeout_minutes)
                
                # Update stale running/pending requests to failed
                stale_requests = (
                    db.query(RequestCache)
                    .filter(RequestCache.start_time < timeout)
                    .filter(RequestCache.status.in_(['pending', 'running']))
                    .all()
                )

                for request in stale_requests:
                    request.status = 'failed'
                    request.error_message = 'Request timed out'
                    request.details = None

                db.commit()

        except Exception as e:
            logger.error(f"Error cleaning up stale entries: {e}")
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

    def _get_latest_request(self, url: str, store: str, db: Session) -> Optional[RequestCache]:
        """Get the latest request for a URL."""
        return (
            db.query(RequestCache)
            .filter(RequestCache.url == url, RequestCache.store == store)
            .order_by(RequestCache.update_time.desc())
            .first()
        )

    async def update_cache_with_result(self, url: str, store_name: str, product_info: Dict[str, Any], job_id: str):
        """Update cache with product information."""
        try:
            # Update request cache
            cache_entry = (
                self.db.query(RequestCache)
                .filter(RequestCache.url == url)
                .filter(RequestCache.store == store_name)
                .filter(RequestCache.job_id == job_id)
                .first()
            )

            if cache_entry:
                cache_entry.status = "completed"
                cache_entry.price_found = True
                cache_entry.update_time = datetime.now(timezone.utc)
            else:
                cache_entry = RequestCache(
                    store=store_name,
                    url=url,
                    job_id=job_id,
                    status="completed",
                    price_found=True,
                    start_time=datetime.now(timezone.utc),
                    update_time=datetime.now(timezone.utc)
                )
                self.db.add(cache_entry)

            # Update products table
            product = Product(
                store=store_name,
                url=url,  # Use original URL
                name=product_info.get("name"),
                price=product_info.get("price"),
                price_string=product_info.get("price_string"),
                price_per_unit=product_info.get("price_per_unit"),
                price_per_unit_string=product_info.get("price_per_unit_string"),
                store_id=product_info.get("store_id"),
                store_address=product_info.get("store_address"),
                store_zip=product_info.get("store_zip"),
                brand=product_info.get("brand"),
                sku=product_info.get("sku"),
                category=product_info.get("category"),
                timestamp=datetime.now(timezone.utc)
            )
            self.db.add(product)
            self.db.commit()

        except Exception as e:
            self.logger.error(f"Error updating cache: {e}")
            self.db.rollback()
            raise

    def update_cache_with_error(self, url: str, store: str, error_message: str) -> None:
        """Update cache with error result."""
        try:
            with get_db() as db:
                request = (
                    db.query(RequestCache)
                    .filter(RequestCache.url == url)
                    .filter(RequestCache.store == store)
                    .first()
                )

                if not request:
                    request = RequestCache(url=url, store=store)
                    db.add(request)

                request.status = 'failed'
                request.price_found = False
                request.error_message = error_message
                request.details = None

                db.commit()

        except Exception as e:
            logger.error(f"Error updating cache with error: {e}")
            db.rollback()
            raise 