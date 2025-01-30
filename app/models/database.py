from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timezone, timedelta
from app.schemas.request_schemas import ProductInfo

SQLALCHEMY_DATABASE_URL = "sqlite:///./price_scraping.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

class Product(Base):
    __tablename__ = "product"

    id = Column(Integer, primary_key=True, index=True)
    store = Column(String)
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
    timestamp = Column(DateTime(timezone=True))

    def to_product_info(self) -> ProductInfo:
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
            timestamp=self.timestamp
        )

class PendingRequest(Base):
    __tablename__ = "pending_request"

    id = Column(Integer, primary_key=True, index=True)
    store = Column(String)
    url = Column(String, index=True)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class RequestCache(Base):
    __tablename__ = "request_cache"

    id = Column(Integer, primary_key=True, index=True)
    store = Column(String)
    url = Column(String, index=True)
    job_id = Column(String, unique=True, index=True)
    status = Column(String)  # 'pending', 'completed', 'failed', 'timeout'
    start_time = Column(DateTime(timezone=True))
    update_time = Column(DateTime(timezone=True))
    price_found = Column(Boolean)
    error_message = Column(String)

    @property
    def is_active(self):
        """Check if request is still active (less than 10 minutes old)"""
        if not self.start_time:
            return False
        age = datetime.now(timezone.utc) - self.start_time
        return age < timedelta(minutes=10)

    @property
    def is_stale(self):
        """Check if request is stale (more than 24 hours old)"""
        if not self.update_time:
            return True
        age = datetime.now(timezone.utc) - self.update_time
        return age > timedelta(hours=24)

# Create tables
Base.metadata.create_all(bind=engine)
