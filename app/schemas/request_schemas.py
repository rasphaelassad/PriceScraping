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
        try:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            result = dt.astimezone(timezone.utc)
            logger.debug(f"Input was datetime object, returning: {result}")
            return result
        except Exception as e:
            logger.error(f"Error converting datetime to UTC: {e}")
            return datetime.now(timezone.utc)
    
    # If it's a string
    if isinstance(dt, str):
        try:
            # Try multiple formats
            for fmt in [
                "%Y-%m-%dT%H:%M:%S%z",  # ISO format with timezone
                "%Y-%m-%dT%H:%M:%S.%f%z",  # ISO format with microseconds and timezone
                "%Y-%m-%d %H:%M:%S%z",  # Standard format with timezone
                "%Y-%m-%dT%H:%M:%S",  # ISO format without timezone
                "%Y-%m-%d %H:%M:%S",  # Standard format without timezone
            ]:
                try:
                    parsed = datetime.strptime(dt.replace('Z', '+0000'), fmt)
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=timezone.utc)
                    result = parsed.astimezone(timezone.utc)
                    logger.debug(f"Successfully parsed string input to datetime: {result}")
                    return result
                except ValueError:
                    continue
            
            # If none of the formats worked, try timestamp
            parsed = datetime.fromtimestamp(float(dt), timezone.utc)
            logger.debug(f"Parsed string as timestamp: {parsed}")
            return parsed
            
        except Exception as e:
            logger.error(f"Failed to parse string as datetime: {e}")
            return datetime.now(timezone.utc)
    
    # If it's a number (timestamp)
    if isinstance(dt, (int, float)):
        try:
            result = datetime.fromtimestamp(float(dt), timezone.utc)
            logger.debug(f"Converted numeric timestamp to datetime: {result}")
            return result
        except Exception as e:
            logger.error(f"Failed to convert numeric timestamp: {e}")
            return datetime.now(timezone.utc)
    
    # For any other type, return current UTC time
    now = datetime.now(timezone.utc)
    logger.debug(f"Unhandled input type: {type(dt)}, returning current UTC time: {now}")
    return now

class PriceRequest(BaseModel):
    store_name: str
    urls: List[HttpUrl]
    start_time: Optional[datetime] = None

    @field_validator('store_name')
    def validate_store_name(cls, v):
        if not v:
            raise ValueError("Store name cannot be empty")
        if not v.strip():
            raise ValueError("Store name cannot be whitespace")
        if len(v) > 255:
            raise ValueError("Store name too long (max 255 characters)")
        return v.lower().strip()

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

    @field_validator('store')
    def validate_store(cls, v):
        if not v:
            raise ValueError("Store cannot be empty")
        if not v.strip():
            raise ValueError("Store cannot be whitespace")
        if len(v) > 255:
            raise ValueError("Store name too long (max 255 characters)")
        return v.lower().strip()

    @field_validator('url')
    def validate_url(cls, v):
        if not v:
            raise ValueError("URL cannot be empty")
        if len(v) > 1024:
            raise ValueError("URL too long (max 1024 characters)")
        return str(v)

    @field_validator('name')
    def validate_name(cls, v):
        if not v:
            raise ValueError("Product name cannot be empty")
        if not v.strip():
            raise ValueError("Product name cannot be whitespace")
        if len(v) > 512:
            raise ValueError("Product name too long (max 512 characters)")
        return v.strip()

    @field_validator('price')
    def validate_price(cls, v):
        if v is not None:
            if v < 0:
                raise ValueError("Price cannot be negative")
            if v > 1000000:  # $1M limit
                raise ValueError("Price exceeds maximum allowed value")
        return v

    @field_validator('price_per_unit')
    def validate_price_per_unit(cls, v):
        if v is not None:
            if v < 0:
                raise ValueError("Price per unit cannot be negative")
            if v > 1000000:  # $1M limit
                raise ValueError("Price per unit exceeds maximum allowed value")
        return v

    @field_validator('store_id')
    def validate_store_id(cls, v):
        if v is not None:
            if len(v) > 64:
                raise ValueError("Store ID too long (max 64 characters)")
        return v

    @field_validator('store_zip')
    def validate_store_zip(cls, v):
        if v is not None:
            if len(v) > 16:
                raise ValueError("Store ZIP too long (max 16 characters)")
        return v

    @field_validator('timestamp', mode='before')
    def ensure_timestamp_utc(cls, v):
        return ensure_utc_datetime(v)

class RequestStatus(BaseModel):
    VALID_STATUSES = {'completed', 'running', 'failed', 'timeout', 'pending'}
    
    status: str
    job_id: Optional[str] = None
    start_time: Optional[datetime] = None
    elapsed_time_seconds: float = 0.0
    remaining_time_seconds: Optional[float] = 0.0
    price_found: Optional[bool] = False
    error_message: Optional[str] = None
    details: Optional[str] = None

    @field_validator('status')
    def validate_status(cls, v):
        if v not in cls.VALID_STATUSES:
            raise ValueError(f"Invalid status. Must be one of: {', '.join(sorted(cls.VALID_STATUSES))}")
        return v

    @field_validator('job_id')
    def validate_job_id(cls, v):
        if v is not None:
            if len(v) > 128:
                raise ValueError("Job ID too long (max 128 characters)")
        return v

    @field_validator('elapsed_time_seconds')
    def validate_elapsed_time(cls, v):
        if v < 0:
            raise ValueError("Elapsed time cannot be negative")
        if v > 86400:  # 24 hours
            raise ValueError("Elapsed time exceeds maximum allowed value (24 hours)")
        return v

    @field_validator('remaining_time_seconds')
    def validate_remaining_time(cls, v):
        if v is not None:
            if v < 0:
                return 0.0
            if v > 86400:  # 24 hours
                raise ValueError("Remaining time exceeds maximum allowed value (24 hours)")
        return v

    @field_validator('error_message')
    def validate_error_message(cls, v):
        if v is not None:
            if len(v) > 1024:
                # Truncate long error messages
                return v[:1021] + "..."
        return v

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