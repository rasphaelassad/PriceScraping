from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional
from app.models.database import RequestCache, Product
from app.schemas.request_schemas import RequestStatus, ProductInfo
from app.core.logging_config import get_logger

logger = get_logger(__name__)

class RequestCacheService:
    def __init__(self, db: Session):
        self.db = db

    def cleanup_stale_entries(self):
        """Clean up stale cache entries (older than 24 hours)"""
        cleanup_time = datetime.now(timezone.utc) - timedelta(hours=24)
        self.db.query(RequestCache).filter(RequestCache.update_time < cleanup_time).delete()
        self.db.commit()

    def get_cache_entry(self, url: str, store: str) -> Optional[RequestCache]:
        """Get the most recent cache entry for a URL"""
        return (
            self.db.query(RequestCache)
            .filter(RequestCache.url == url)
            .filter(RequestCache.store == store)
            .order_by(RequestCache.update_time.desc())
            .first()
        )

    def get_cached_product(self, url: str, store: str) -> Optional[Product]:
        """Get the most recent product for a URL"""
        return (
            self.db.query(Product)
            .filter(Product.url == url)
            .filter(Product.store == store)
            .order_by(Product.timestamp.desc())
            .first()
        )

    def create_request_status(self, cache_entry: RequestCache) -> RequestStatus:
        """Create a RequestStatus object from a cache entry"""
        now = datetime.now(timezone.utc)
        elapsed_time = (now - cache_entry.start_time).total_seconds()
        
        return RequestStatus(
            status=cache_entry.status,
            job_id=cache_entry.job_id,
            start_time=cache_entry.start_time,
            elapsed_time_seconds=elapsed_time,
            remaining_time_seconds=0 if cache_entry.status == 'completed' else max(0, 600 - elapsed_time),
            price_found=cache_entry.price_found,
            error_message=cache_entry.error_message,
            details=f"Request {cache_entry.status} in {elapsed_time:.1f} seconds"
        )
