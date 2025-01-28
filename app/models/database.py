from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timezone
from typing import Optional
import os
import logging
import sqlite3

# Configure logging
logger = logging.getLogger(__name__)

# Register adapters for SQLite to handle timezone-aware datetimes
def adapt_datetime(dt):
    """Convert datetime to UTC ISO format string"""
    logger.debug(f"adapt_datetime input: {dt}, type: {type(dt)}")
    if dt is None:
        return None
    try:
        if isinstance(dt, bytes):
            dt = dt.decode()
        if isinstance(dt, str):
            dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
        if not isinstance(dt, datetime):
            logger.error(f"Cannot convert {type(dt)} to datetime")
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt = dt.astimezone(timezone.utc)
        result = dt.isoformat()
        logger.debug(f"adapt_datetime output: {result}")
        return result
    except Exception as e:
        logger.error(f"Error in adapt_datetime: {e}")
        return None

def convert_datetime(val):
    """Convert ISO format string to UTC datetime"""
    logger.debug(f"convert_datetime input: {val}, type: {type(val)}")
    if val is None:
        return None
    try:
        if isinstance(val, bytes):
            val = val.decode()
        if isinstance(val, str):
            dt = datetime.fromisoformat(val.replace('Z', '+00:00'))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            result = dt.astimezone(timezone.utc)
            logger.debug(f"convert_datetime output: {result}, tzinfo: {result.tzinfo}")
            return result
        if isinstance(val, datetime):
            if val.tzinfo is None:
                val = val.replace(tzinfo=timezone.utc)
            result = val.astimezone(timezone.utc)
            logger.debug(f"convert_datetime output: {result}, tzinfo: {result.tzinfo}")
            return result
        logger.error(f"Cannot convert {type(val)} to datetime")
        return None
    except Exception as e:
        logger.error(f"Error in convert_datetime: {e}")
        return None

sqlite3.register_adapter(datetime, adapt_datetime)
sqlite3.register_converter("datetime", convert_datetime)

# Create database directory if it doesn't exist
os.makedirs('data', exist_ok=True)

# SQLite URL with timezone support
SQLALCHEMY_DATABASE_URL = os.getenv('DATABASE_URL', "sqlite:///data/scraper.db?mode=rw&timezone=UTC")

# Create database engine with timezone support
if SQLALCHEMY_DATABASE_URL.startswith('sqlite'):
    # SQLite specific configuration
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        connect_args={
            "check_same_thread": False,
            "detect_types": sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES
        },
        pool_pre_ping=True  # Enable foreign key support
    )
else:
engine = create_engine(SQLALCHEMY_DATABASE_URL)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create base class for models
Base = declarative_base()

def get_utc_now():
    """Helper function to get current UTC time"""
    return datetime.now(timezone.utc)

def ensure_utc_datetime(dt):
    """Helper function to ensure a datetime is timezone-aware UTC"""
    if dt is None:
        return get_utc_now()
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

class Product(Base):
    __tablename__ = "product"

    id = Column(Integer, primary_key=True, index=True)
    store = Column(String, index=True)
    url = Column(String, index=True)
    name = Column(String)
    price = Column(Float)
    price_string = Column(String)
    price_per_unit = Column(Float)
    price_per_unit_string = Column(String)
    store_id = Column(String)
    store_address = Column(String)
    store_zip = Column(String)
    brand = Column(String)
    sku = Column(String)
    category = Column(String)
    timestamp = Column(DateTime(timezone=True), default=get_utc_now)

    @classmethod
    def from_product_info(cls, product_info):
        """Create from ProductInfo model"""
        logger.debug(f"Creating Product from ProductInfo - timestamp: {product_info.timestamp}, type: {type(product_info.timestamp)}")
        timestamp = ensure_utc_datetime(product_info.timestamp)
        logger.debug(f"Ensured UTC timestamp: {timestamp}, tzinfo: {timestamp.tzinfo}")
        
        return cls(
            store=product_info.store,
            url=product_info.url,
            name=product_info.name,
            price=product_info.price,
            price_string=product_info.price_string,
            price_per_unit=product_info.price_per_unit,
            price_per_unit_string=product_info.price_per_unit_string,
            store_id=product_info.store_id,
            store_address=product_info.store_address,
            store_zip=product_info.store_zip,
            brand=product_info.brand,
            sku=product_info.sku,
            category=product_info.category,
            timestamp=timestamp
        )

    def to_product_info(self):
        """Convert to ProductInfo model"""
        from app.schemas.request_schemas import ProductInfo
        logger.debug(f"Converting Product to ProductInfo - timestamp: {self.timestamp}, type: {type(self.timestamp)}")
        timestamp = ensure_utc_datetime(self.timestamp)
        logger.debug(f"Ensured UTC timestamp: {timestamp}, tzinfo: {timestamp.tzinfo}")
        
        return ProductInfo(
            store=self.store,
            url=self.url,
            name=self.name,
            price=self.price,
            price_string=self.price_string,
            price_per_unit=self.price_per_unit,
            price_per_unit_string=self.price_per_unit_string,
            store_id=self.store_id,
            store_address=self.store_address,
            store_zip=self.store_zip,
            brand=self.brand,
            sku=self.sku,
            category=self.category,
            timestamp=timestamp
        )

class RequestCache(Base):
    __tablename__ = "request_cache"

    id = Column(Integer, primary_key=True, index=True)
    store = Column(String, index=True)
    url = Column(String, index=True)
    job_id = Column(String, index=True)
    status = Column(String, index=True)  # 'pending', 'completed', 'failed', 'timeout'
    start_time = Column(DateTime(timezone=True), default=get_utc_now)
    update_time = Column(DateTime(timezone=True), default=get_utc_now)
    price_found = Column(Boolean, default=False)
    error_message = Column(String, nullable=True)

    @property
    def is_active(self) -> bool:
        """Check if the request is still active (less than 10 minutes old)"""
        if self.status in ['completed', 'failed', 'timeout']:
            return False
        now = datetime.now(timezone.utc)
        logger.debug(f"Checking is_active - now: {now}, start_time: {self.start_time}, tzinfo: {self.start_time.tzinfo}")
        return (now - self.start_time).total_seconds() < 600  # 10 minutes

    @property
    def is_stale(self) -> bool:
        """Check if the request is stale (older than 24 hours)"""
        now = datetime.now(timezone.utc)
        logger.debug(f"Checking is_stale - now: {now}, update_time: {self.update_time}, tzinfo: {self.update_time.tzinfo}")
        return (now - self.update_time).total_seconds() > 86400  # 24 hours

class PendingRequest(Base):
    __tablename__ = "pending_request"

    id = Column(Integer, primary_key=True, index=True)
    store = Column(String, index=True)
    url = Column(String, unique=True, index=True)
    timestamp = Column(DateTime(timezone=True), default=get_utc_now)

# Create all tables
Base.metadata.create_all(bind=engine) 