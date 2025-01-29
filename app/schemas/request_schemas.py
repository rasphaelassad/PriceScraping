from pydantic import BaseModel, HttpUrl, field_validator
from typing import List, Optional, Dict
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

def ensure_utc_datetime(dt):
    """Helper function to ensure a datetime is timezone-aware UTC"""
    logger.debug(f"ensure_utc_datetime called with value: {dt}, type: {type(dt)}")
    
    if dt is None:
        now = datetime.now(timezone.utc)
        logger.debug(f"Input was None, returning current UTC time: {now}")
        return now
    
    # If it's already a datetime object
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        result = dt.astimezone(timezone.utc)
        logger.debug(f"Input was datetime object, returning: {result}")
        return result
    
    # If it's a string
    if isinstance(dt, str):
        try:
            # Handle both ISO format and other string formats
            if 'Z' in dt:
                dt = dt.replace('Z', '+00:00')
            try:
                parsed = datetime.fromisoformat(dt)
            except ValueError:
                # Try parsing as timestamp if ISO format fails
                parsed = datetime.fromtimestamp(float(dt), timezone.utc)
            
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            result = parsed.astimezone(timezone.utc)
            logger.debug(f"Successfully parsed string input to datetime: {result}")
            return result
        except Exception as e:
            logger.error(f"Failed to parse string as datetime: {e}")
            now = datetime.now(timezone.utc)
            logger.debug(f"Returning current UTC time due to parsing error: {now}")
            return now
    
    # If it's a number (timestamp)
    if isinstance(dt, (int, float)):
        try:
            result = datetime.fromtimestamp(dt, timezone.utc)
            logger.debug(f"Converted numeric timestamp to datetime: {result}")
            return result
        except Exception as e:
            logger.error(f"Failed to convert numeric timestamp: {e}")
            now = datetime.now(timezone.utc)
            logger.debug(f"Returning current UTC time due to conversion error: {now}")
            return now
    
    # For any other type, return current UTC time
    now = datetime.now(timezone.utc)
    logger.debug(f"Unhandled input type: {type(dt)}, returning current UTC time: {now}")
    return now

class PriceRequest(BaseModel):
    store_name: str
    urls: List[HttpUrl]
    start_time: Optional[datetime] = None

    @field_validator('start_time', mode='before')
    def ensure_start_time_utc(cls, v):
        return ensure_utc_datetime(v)

class ProductInfo(BaseModel):
    store: str
    url: str
    name: str
    price: Optional[float] = None
    price_string: Optional[str] = None
    price_per_unit: Optional[float] = None
    price_per_unit_string: Optional[str] = None
    store_id: Optional[str] = None
    store_address: Optional[str] = None
    store_zip: Optional[str] = None
    brand: Optional[str] = None
    sku: Optional[str] = None
    category: Optional[str] = None
    timestamp: datetime

    @field_validator('timestamp', mode='before')
    def ensure_timestamp_utc(cls, v):
        return ensure_utc_datetime(v)

class RequestStatus(BaseModel):
    status: str  # 'completed', 'running', 'failed', 'timeout'
    job_id: Optional[str] = None
    start_time: Optional[datetime] = None
    elapsed_time_seconds: float = 0.0
    remaining_time_seconds: Optional[float] = 0.0
    price_found: Optional[bool] = False
    error_message: Optional[str] = None
    details: Optional[str] = None

    @field_validator('start_time', mode='before')
    def ensure_start_time_utc(cls, v):
        logger.debug(f"Validating start_time - value: {v}, type: {type(v)}")
        try:
            result = ensure_utc_datetime(v)
            logger.debug(f"Validated start_time - result: {result}, type: {type(result)}")
            return result
        except Exception as e:
            logger.error(f"Error validating start_time: {e}")
            return datetime.now(timezone.utc)

class UrlResult(BaseModel):
    result: Optional[ProductInfo]
    request_status: RequestStatus

class PriceResponse(BaseModel):
    results: Dict[str, UrlResult]
    error: Optional[str] = None 