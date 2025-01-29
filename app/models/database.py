from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, create_engine, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime, timezone
from typing import Optional, Generator
from contextlib import contextmanager
import os
import logging
from app.schemas.request_schemas import ProductInfo
import time

# Configure logging
logger = logging.getLogger(__name__)

class TimeUtil:
    """Utility class for handling timezone-aware datetime operations"""
    @staticmethod
    def ensure_utc(dt: Optional[datetime]) -> datetime:
        """Ensure a datetime is UTC timezone-aware"""
        try:
            if dt is None:
                return datetime.now(timezone.utc)
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception as e:
            logger.error(f"Error ensuring UTC timezone: {e}")
            return datetime.now(timezone.utc)

    @staticmethod
    def get_utc_now() -> datetime:
        """Get current UTC datetime"""
        try:
            return datetime.now(timezone.utc)
        except Exception as e:
            logger.error(f"Error getting UTC now: {e}")
            # Fallback to non-timezone aware datetime and convert it
            return datetime.now().replace(tzinfo=timezone.utc)

    @staticmethod
    def get_seconds_since(dt: datetime) -> float:
        """Get seconds elapsed since given datetime"""
        try:
            return (TimeUtil.get_utc_now() - TimeUtil.ensure_utc(dt)).total_seconds()
        except Exception as e:
            logger.error(f"Error calculating seconds since: {e}")
            return 0.0

class DatabaseConfig:
    """Database configuration settings"""
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    DB_FILE = os.path.join(BASE_DIR, "price_scraper.db")
    DEFAULT_URL = f"sqlite:///{DB_FILE}"

# Database URL configuration
SQLALCHEMY_DATABASE_URL = os.getenv('DATABASE_URL', DatabaseConfig.DEFAULT_URL)

# Create database engine with SQLite-specific configuration
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False} if SQLALCHEMY_DATABASE_URL.startswith('sqlite') else {}
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create base class for models
Base = declarative_base()

class Product(Base):
    """Product model with improved type hints and documentation"""
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    store = Column(String(255), index=True, nullable=False)
    url = Column(String(1024), index=True, nullable=False)
    name = Column(String(512), nullable=False)
    price = Column(Float, nullable=True)
    price_string = Column(String(64), nullable=True)
    price_per_unit = Column(Float, nullable=True)
    price_per_unit_string = Column(String(64), nullable=True)
    store_id = Column(String(64), nullable=True)
    store_address = Column(String(512), nullable=True)
    store_zip = Column(String(16), nullable=True)
    brand = Column(String(255), nullable=True)
    sku = Column(String(64), nullable=True)
    category = Column(String(255), nullable=True)
    timestamp = Column(DateTime(timezone=True), default=TimeUtil.get_utc_now, nullable=False)

    __table_args__ = (
        # Ensure unique combination of store, url, and timestamp
        UniqueConstraint('store', 'url', 'timestamp', name='uix_store_url_timestamp'),
    )

    @classmethod
    def from_product_info(cls, product_info: 'ProductInfo') -> 'Product':
        """Create a Product instance from ProductInfo with proper error handling"""
        try:
            logger.debug(f"Creating Product from ProductInfo - timestamp: {product_info.timestamp}")
            return cls(
                store=product_info.store,
                url=str(product_info.url),
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
                timestamp=TimeUtil.ensure_utc(product_info.timestamp)
            )
        except Exception as e:
            logger.error(f"Error creating Product from ProductInfo: {str(e)}")
            raise

    def to_product_info(self) -> 'ProductInfo':
        """Convert to ProductInfo with proper error handling"""
        try:
            logger.debug(f"Converting Product to ProductInfo - timestamp: {self.timestamp}")
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
                timestamp=TimeUtil.ensure_utc(self.timestamp)
            )
        except Exception as e:
            logger.error(f"Error converting Product to ProductInfo: {str(e)}")
            raise

class RequestCache(Base):
    """Request cache model with improved type hints and documentation"""
    __tablename__ = "request_cache"

    id = Column(Integer, primary_key=True, index=True)
    store = Column(String(255), index=True, nullable=False)
    url = Column(String(1024), index=True, nullable=False)
    job_id = Column(String(128), index=True, nullable=False)
    status = Column(String(32), index=True, nullable=False)  # 'pending', 'completed', 'failed', 'timeout'
    start_time = Column(DateTime(timezone=True), default=TimeUtil.get_utc_now, nullable=False)
    update_time = Column(DateTime(timezone=True), default=TimeUtil.get_utc_now, nullable=False)
    price_found = Column(Boolean, default=False, nullable=False)
    error_message = Column(String(1024), nullable=True)

    __table_args__ = (
        # Ensure unique combination of store and url
        UniqueConstraint('store', 'url', name='uix_store_url'),
    )

    ACTIVE_THRESHOLD = 600  # 10 minutes in seconds
    STALE_THRESHOLD = 86400  # 24 hours in seconds

    @property
    def is_active(self) -> bool:
        """Check if the request is still active (less than 10 minutes old)"""
        if self.status in ['completed', 'failed', 'timeout']:
            return False
        return TimeUtil.get_seconds_since(self.start_time) < self.ACTIVE_THRESHOLD

    @property
    def is_stale(self) -> bool:
        """Check if the request is stale (older than 24 hours)"""
        return TimeUtil.get_seconds_since(self.update_time) > self.STALE_THRESHOLD

def retry_operation(operation, max_retries=3, delay=1):
    """Retry a database operation with exponential backoff"""
    for attempt in range(max_retries):
        try:
            return operation()
        except SQLAlchemyError as e:
            if attempt == max_retries - 1:
                raise
            logger.warning(f"Database operation failed (attempt {attempt + 1}/{max_retries}): {e}")
            time.sleep(delay * (2 ** attempt))

@contextmanager
def get_db() -> Generator[Session, None, None]:
    """Context manager for database sessions with proper error handling and retry logic"""
    db = None
    try:
        def create_session():
            nonlocal db
            db = SessionLocal()
            return db
        
        db = retry_operation(create_session)
        yield db
    except SQLAlchemyError as e:
        logger.error(f"Database error occurred: {str(e)}")
        if db:
            db.rollback()
        raise
    except Exception as e:
        logger.error(f"Unexpected error in database session: {str(e)}")
        if db:
            db.rollback()
        raise
    finally:
        if db:
            try:
                db.close()
            except Exception as e:
                logger.error(f"Error closing database connection: {str(e)}")

def init_db(testing: bool = False):
    """Initialize database and create all tables with retry logic"""
    def create_tables():
        Base.metadata.create_all(bind=engine)
        logger.info("Successfully created all database tables")

    try:
        retry_operation(create_tables)
    except Exception as e:
        logger.error(f"Database initialization failed: {str(e)}")
        raise

# Only initialize database if not in testing mode
if not os.getenv('TESTING'):
    init_db() 