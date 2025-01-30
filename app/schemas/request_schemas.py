from pydantic import BaseModel, HttpUrl, validator
from typing import List, Optional, Dict
from datetime import datetime, timezone
from enum import Enum

class RequestStatusEnum(str, Enum):
    SUCCESS = "SUCCESS"
    PENDING = "PENDING"
    ERROR = "ERROR"

class PriceRequest(BaseModel):
    store: str
    urls: List[HttpUrl]

    @validator('store')
    def normalize_store(cls, v):
        return v.lower()

class ProductInfo(BaseModel):
    store: str
    url: str
    name: Optional[str]
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
    timestamp: Optional[datetime]

    @validator('timestamp', pre=True)
    def ensure_timezone(cls, v):
        if v is None:
            return datetime.now(timezone.utc)
        if isinstance(v, datetime):
            if v.tzinfo is None:
                return v.replace(tzinfo=timezone.utc)
            return v
        raise ValueError('Invalid datetime format')

    @validator('store')
    def normalize_store(cls, v):
        return v.lower()

class UrlResult(BaseModel):
    status: RequestStatusEnum
    product: Optional[ProductInfo] = None
    error: Optional[str] = None

class PriceResponse(BaseModel):
    results: Dict[str, UrlResult]