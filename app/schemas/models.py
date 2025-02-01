from pydantic import BaseModel, HttpUrl, field_validator
from typing import List, Optional
from datetime import datetime

class ProductInfo(BaseModel):
    """Product information returned by scrapers."""
    store: str
    url: str
    name: str
    price: Optional[float] = None
    price_string: Optional[str] = None
    store_id: Optional[str] = None
    store_address: Optional[str] = None
    store_zip: Optional[str] = None
    brand: Optional[str] = None
    sku: Optional[str] = None
    category: Optional[str] = None

class RequestStatus(BaseModel):
    """Status information for a scraping request."""
    status: str  # 'completed', 'failed', 'pending'
    job_id: str
    start_time: datetime
    elapsed_time_seconds: float
    error_message: Optional[str] = None

class PriceRequest(BaseModel):
    """Request for getting prices from multiple URLs."""
    urls: List[HttpUrl]

    @field_validator('urls')
    def validate_urls(cls, v):
        if not v:
            raise ValueError("URLs list cannot be empty")
        if len(v) > 10:
            raise ValueError("Maximum of 10 URLs allowed per request")
        # Check for duplicate URLs
        url_strings = [str(url) for url in v]
        if len(url_strings) != len(set(url_strings)):
            raise ValueError("Duplicate URLs are not allowed")
        # Check URL lengths
        for url in url_strings:
            if len(url) > 1024:
                raise ValueError(f"URL too long (max 1024 characters): {url[:50]}...")
        return v 