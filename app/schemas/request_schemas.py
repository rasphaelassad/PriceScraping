from pydantic import BaseModel, HttpUrl, validator
from typing import List, Optional, Dict
from datetime import datetime, timezone

def ensure_utc_datetime(dt):
    """Helper function to ensure a datetime is timezone-aware UTC"""
    if dt is None:
        return datetime.now(timezone.utc)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

class PriceRequest(BaseModel):
    store_name: str
    urls: List[HttpUrl]

class ProductInfo(BaseModel):
    store: str
    url: str
    name: str
    price: Optional[float]
    price_string: Optional[str]
    price_per_unit: Optional[float]
    price_per_unit_string: Optional[str]
    store_id: Optional[str]
    store_address: Optional[str]
    store_zip: Optional[str]
    brand: Optional[str]
    sku: Optional[str]
    category: Optional[str]
    timestamp: datetime

    @validator('timestamp', pre=True)
    def ensure_timestamp_utc(cls, v):
        return ensure_utc_datetime(v)

class RequestStatus(BaseModel):
    status: str  # 'completed', 'running', 'failed', 'timeout'
    job_id: Optional[str]
    start_time: datetime
    elapsed_time_seconds: float
    remaining_time_seconds: Optional[float]
    price_found: Optional[bool]
    error_message: Optional[str]
    details: Optional[str]

    @validator('start_time', pre=True)
    def ensure_start_time_utc(cls, v):
        return ensure_utc_datetime(v)

class UrlResult(BaseModel):
    result: Optional[ProductInfo]
    request_status: RequestStatus

class PriceResponse(BaseModel):
    results: Dict[str, UrlResult]
    error: Optional[str] = None 