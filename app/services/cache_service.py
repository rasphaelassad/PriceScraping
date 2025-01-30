from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from app.models.database import Product, PendingRequest, RequestCache
from app.schemas.request_schemas import ProductInfo, RequestStatus, UrlResult
from app.core.logging_config import get_logger

logger = get_logger(__name__)

class CacheService:
    def __init__(self, db: Session):
        self.db = db

    def get_cached_results(self, urls: List[str]) -> Dict[str, ProductInfo]:
        """Get cached results that are less than 24 hours old"""
        cached_products = {}
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=24)
        
        for url in urls:
            cached = (
                self.db.query(Product)
                .filter(Product.url == str(url))
                .filter(Product.timestamp > cutoff_time)
                .first()
            )
            if cached:
                logger.debug(f"Found cached result for URL: {url}")
                cached_products[str(url)] = cached.to_product_info()
        
        return cached_products

    def get_pending_requests(self, store: str, urls: List[str]) -> Dict[str, bool]:
        """Get URLs that are currently being processed"""
        pending = {}
        self._cleanup_old_pending_requests()
        
        for url in urls:
            pending_request = (
                self.db.query(PendingRequest)
                .filter(PendingRequest.url == str(url))
                .filter(PendingRequest.store == store)
                .first()
            )
            if pending_request:
                pending[str(url)] = True
        
        return pending

    def _cleanup_old_pending_requests(self):
        """Clean up old pending requests (older than 10 minutes)"""
        cleanup_time = datetime.now(timezone.utc) - timedelta(minutes=10)
        self.db.query(PendingRequest).filter(PendingRequest.timestamp < cleanup_time).delete()
        self.db.commit()

    def add_pending_requests(self, store: str, urls: List[str]):
        """Add URLs to pending requests"""
        for url in urls:
            url_str = str(url)
            existing = self.db.query(PendingRequest).filter(PendingRequest.url == url_str).first()
            if existing:
                existing.timestamp = datetime.now(timezone.utc)
            else:
                pending = PendingRequest(store=store, url=url_str)
                self.db.add(pending)
        self.db.commit()

    def remove_pending_requests(self, urls: List[str]):
        """Remove URLs from pending requests"""
        for url in urls:
            self.db.query(PendingRequest).filter(PendingRequest.url == str(url)).delete()
        self.db.commit()

    def cache_results(self, results: Dict[str, UrlResult]):
        """Cache the results in the database"""
        for url, result in results.items():
            if result.product and result.product.price is not None:
                existing = self.db.query(Product).filter(Product.url == url).first()
                if existing:
                    existing.update_from_product_info(result.product)
                    existing.timestamp = datetime.now(timezone.utc)
                else:
                    product = Product.from_product_info(url, result.product)
                    self.db.add(product)
        self.db.commit()

    def get_request_cache(self, url: str, store: str) -> Optional[RequestCache]:
        """Get the most recent cache entry for a URL"""
        return (
            self.db.query(RequestCache)
            .filter(RequestCache.url == url)
            .filter(RequestCache.store == store)
            .order_by(RequestCache.update_time.desc())
            .first()
        )

    def cleanup_stale_cache(self):
        """Clean up stale cache entries (older than 24 hours)"""
        cleanup_time = datetime.now(timezone.utc) - timedelta(hours=24)
        self.db.query(RequestCache).filter(RequestCache.update_time < cleanup_time).delete()
        self.db.commit()

    def get_product_by_url(self, url: str, store: str) -> Optional[Product]:
        """Get the most recent product entry for a URL"""
        return (
            self.db.query(Product)
            .filter(Product.url == url)
            .filter(Product.store == store)
            .order_by(Product.timestamp.desc())
            .first()
        )
