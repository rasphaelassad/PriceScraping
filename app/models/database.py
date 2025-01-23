from sqlalchemy import Column, Integer, String, Float, DateTime, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os

# Create the database directory if it doesn't exist
os.makedirs('data', exist_ok=True)

# Create database engine
SQLALCHEMY_DATABASE_URL = "sqlite:///./data/scraper.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create base class for models
Base = declarative_base()

class Product(Base):
    __tablename__ = "product"

    id = Column(Integer, primary_key=True, index=True)
    store = Column(String, index=True)
    url = Column(String, unique=True, index=True)
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
    timestamp = Column(DateTime, default=datetime.now)

    @classmethod
    def from_product_info(cls, product_info):
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
            timestamp=product_info.timestamp
        )

    def to_product_info(self):
        from app.schemas.request_schemas import ProductInfo
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

# Create all tables
Base.metadata.create_all(bind=engine) 