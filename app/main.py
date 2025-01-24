from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from app.schemas.request_schemas import PriceRequest, PriceResponse, ProductInfo
from app.scrapers.costco_scraper import CostcoScraper
from app.scrapers.walmart_scraper import WalmartScraper
from app.scrapers.albertsons_scraper import AlbertsonsScraper
from app.scrapers.chefstore_scraper import ChefStoreScraper
from app.models.database import SessionLocal, Product, PendingRequest, Base
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any
import logging
from sqlalchemy import inspect
from fastapi.responses import JSONResponse
import httpx
import time
import asyncio

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Store Price API")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Dependency to get database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/")
def hello_world():
    return {'message': 'Hello from FastAPI'}

SUPPORTED_STORES = {
    "walmart": WalmartScraper,
    "albertsons": AlbertsonsScraper,
    "chefstore": ChefStoreScraper,
    "costco": CostcoScraper,
}

def get_cached_results(db: Session, urls: list[str]) -> dict:
    """Get cached results that are less than 24 hours old"""
    cached_products = {}
    cutoff_time = datetime.now(timezone.utc) - timedelta(hours=24)
    
    for url in urls:
        cached = (
            db.query(Product)
            .filter(Product.url == str(url))
            .filter(Product.timestamp > cutoff_time)
            .first()
        )
        if cached:
            cached_products[str(url)] = cached.to_product_info()
    
    return cached_products

def get_pending_requests(db: Session, store: str, urls: list[str]) -> dict:
    """Get URLs that are currently being processed"""
    pending = {}
    # Clean up old pending requests (older than 10 minutes)
    cleanup_time = datetime.now(timezone.utc) - timedelta(minutes=10)
    db.query(PendingRequest).filter(PendingRequest.timestamp < cleanup_time).delete()
    db.commit()
    
    for url in urls:
        pending_request = (
            db.query(PendingRequest)
            .filter(PendingRequest.url == str(url))
            .filter(PendingRequest.store == store)
            .first()
        )
        if pending_request:
            pending[str(url)] = True
    
    return pending

def add_pending_requests(db: Session, store: str, urls: list[str]):
    """Add URLs to pending requests"""
    for url in urls:
        url_str = str(url)
        # Check if request already exists
        existing = db.query(PendingRequest).filter(PendingRequest.url == url_str).first()
        if existing:
            # Update timestamp of existing request
            existing.timestamp = datetime.now(timezone.utc)
        else:
            # Create new request
            pending = PendingRequest(store=store, url=url_str)
            db.add(pending)
    db.commit()

def remove_pending_requests(db: Session, urls: list[str]):
    """Remove URLs from pending requests"""
    for url in urls:
        db.query(PendingRequest).filter(PendingRequest.url == str(url)).delete()
    db.commit()

def cache_results(db: Session, results: dict):
    """Cache the results in the database. Skip products with null prices."""
    for url, product_info_dict in results.items():
        if not product_info_dict or product_info_dict.get('price') is None:
            logger.info(f"Skipping product with null price for URL: {url}")
            continue
            
        # Convert dictionary to ProductInfo model
        product_info_dict['timestamp'] = datetime.now(timezone.utc)
        product_info = ProductInfo(**product_info_dict)
            
        # Convert Pydantic Url to string for database storage
        url_str = str(url)
            
        # Check if product exists in cache
        existing = db.query(Product).filter(Product.url == url_str).first()
        if existing:
            # Update existing cache entry
            product_info_dict = product_info.dict()
            for key, value in product_info_dict.items():
                setattr(existing, key, value)
        else:
            # Create new cache entry
            db_product = Product.from_product_info(product_info)
            db.add(db_product)
    
    db.commit()

@app.post("/get-prices")
async def get_prices(request: PriceRequest, db: Session = Depends(get_db)):
    try:
        store_name = request.store_name.lower()
        urls = request.urls
        
        logger.info(f"Creating scraper for store: {store_name}")
        scraper_class = SUPPORTED_STORES.get(store_name)
        
        if not scraper_class:
            raise HTTPException(status_code=400, detail=f"Unsupported store: {store_name}")
        
        # Check cache first
        cached_results = get_cached_results(db, urls)
        if cached_results:
            logger.info("Found cached results")
            return PriceResponse(results=cached_results)
            
        # Check pending requests
        pending = get_pending_requests(db, store_name, urls)
        if pending:
            logger.info("Request already in progress")
            return PriceResponse(results={str(url): None for url in urls})
        
        # Create an instance of the scraper
        scraper = scraper_class()
        
        logger.info(f"Fetching prices for URLs: {urls}")
        
        # Add URLs to pending requests using original URLs
        add_pending_requests(db, store_name, urls)
        
        # Get prices
        results = await scraper.get_prices(urls)
        
        # Convert results to ProductInfo models
        string_results = {}
        for url, price_info in results.items():
            if price_info:
                price_info['timestamp'] = datetime.now(timezone.utc)
                string_results[str(url)] = ProductInfo(**price_info)
            else:
                string_results[str(url)] = None
        
        # Remove URLs from pending requests using original URLs
        remove_pending_requests(db, urls)
        
        # Cache results
        if results:
            cache_results(db, results)
            
        return PriceResponse(results=string_results)
        
    except Exception as e:
        logger.error(f"Error processing request: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/supported-stores")
def get_supported_stores():
    return {"supported_stores": list(SUPPORTED_STORES.keys())}

@app.get("/health")
def health_check():
    return {"status": "healthy"}

@app.get("/table/{table_name}")
def get_table_data(table_name: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    Get all data from a specified database table.
    Currently supports: 'product' and 'pending_request' tables.
    """
    # Get the table class based on name
    table_map = {
        "product": Product,
        "pending_request": PendingRequest
    }
    
    if table_name not in table_map:
        raise HTTPException(
            status_code=400,
            detail=f"Table '{table_name}' not found. Available tables: {', '.join(table_map.keys())}"
        )
    
    try:
        # Query all records from the table
        records = db.query(table_map[table_name]).all()
        
        # Convert records to list of dictionaries
        if table_name == "product":
            data = [
                {
                    "id": record.id,
                    "store": record.store,
                    "url": record.url,
                    "name": record.name,
                    "price": record.price,
                    "price_string": record.price_string,
                    "price_per_unit": record.price_per_unit,
                    "price_per_unit_string": record.price_per_unit_string,
                    "store_id": record.store_id,
                    "store_address": record.store_address,
                    "store_zip": record.store_zip,
                    "brand": record.brand,
                    "sku": record.sku,
                    "category": record.category,
                    "timestamp": record.timestamp.isoformat() if record.timestamp else None
                }
                for record in records
            ]
        else:  # pending_request table
            data = [
                {
                    "id": record.id,
                    "store": record.store,
                    "url": record.url,
                    "timestamp": record.timestamp.isoformat() if record.timestamp else None
                }
                for record in records
            ]
        
        return {
            "table": table_name,
            "count": len(data),
            "data": data
        }
        
    except Exception as e:
        logger.error(f"Error fetching data from table {table_name}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching data from table: {str(e)}"
        )

@app.get("/tables")
def get_tables(db: Session = Depends(get_db)):
    """Get all tables in the database and their structure"""
    try:
        inspector = inspect(db.bind)
        database_info = {}
        
        for table_name in inspector.get_table_names():
            columns = []
            for column in inspector.get_columns(table_name):
                columns.append({
                    "name": column["name"],
                    "type": str(column["type"]),
                    "nullable": column["nullable"]
                })
            
            database_info[table_name] = {
                "columns": columns,
                "row_count": db.query(db.bind.table_metadata.tables[table_name]).count()
            }
            
        return JSONResponse(content=database_info)
    except Exception as e:
        logger.error(f"Error getting database tables: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/raw-scrape")
async def get_raw_html(request: PriceRequest, db: Session = Depends(get_db)):
    """Get raw HTML/JSON response without processing"""
    try:
        store_name = request.store_name.lower()
        urls = request.urls
        
        logger.info(f"Creating scraper for store: {store_name}")
        scraper_class = SUPPORTED_STORES.get(store_name)
        
        if not scraper_class:
            raise HTTPException(status_code=400, detail=f"Unsupported store: {store_name}")
            
        scraper = scraper_class()
        
        logger.info(f"Fetching raw content for URLs: {urls}")
        raw_results = await scraper.get_raw_content(urls)
        
        return JSONResponse(content=raw_results)
        
    except Exception as e:
        logger.error(f"Error processing raw scrape request: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))