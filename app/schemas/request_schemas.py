from pydantic import BaseModel, HttpUrl
from typing import List, Optional, Dict
from datetime import datetime

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

class RequestStatus(BaseModel):
    status: str  # 'completed', 'running', 'failed', 'timeout'
    job_id: Optional[str]
    start_time: datetime
    elapsed_time_seconds: float
    remaining_time_seconds: Optional[float]
    price_found: Optional[bool]
    error_message: Optional[str]
    details: Optional[str]

class UrlResult(BaseModel):
    result: Optional[ProductInfo]
    request_status: RequestStatus

class PriceResponse(BaseModel):
    results: Dict[str, UrlResult]
    error: Optional[str] = None 