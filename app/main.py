from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from app.schemas.request_schemas import PriceRequest, PriceResponse, ProductInfo
from app.scrapers.costco_scraper import CostcoScraper
from app.scrapers.walmart_scraper import WalmartScraper
from app.scrapers.albertsons_scraper import AlbertsonsScraper
from app.scrapers.chefstore_scraper import ChefStoreScraper
from app.models.database import SessionLocal, Product, PendingRequest, Base
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import logging
from typing import List, Dict, Any

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

@app.get("/hello/{name}")
def hello(name: str):
    return {"message": f'Hello from FastAPI, {name}!'}

SUPPORTED_STORES = {
    "walmart": WalmartScraper,
    "albertsons": AlbertsonsScraper,
    "chefstore": ChefStoreScraper,
    "costco": CostcoScraper,
}

def get_cached_results(db: Session, urls: list[str]) -> dict:
    """Get cached results that are less than 24 hours old"""
    cached_products = {}
    cutoff_time = datetime.now(ZoneInfo("UTC")) - timedelta(hours=24)
    
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
    cleanup_time = datetime.now(ZoneInfo("UTC")) - timedelta(minutes=10)
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
        pending = PendingRequest(store=store, url=str(url))
        db.add(pending)
    db.commit()

def remove_pending_requests(db: Session, urls: list[str]):
    """Remove URLs from pending requests"""
    for url in urls:
        db.query(PendingRequest).filter(PendingRequest.url == str(url)).delete()
    db.commit()

def cache_results(db: Session, results: dict):
    """Cache the results in the database. Skip products with null prices."""
    for url, product_info in results.items():
        if not product_info or product_info.price is None:
            logger.info(f"Skipping product with null price for URL: {url}")
            continue
            
        # Check if product exists in cache
        existing = db.query(Product).filter(Product.url == url).first()
        if existing:
            # Update existing cache entry
            product_info_dict = product_info.dict()
            product_info_dict['timestamp'] = datetime.now(ZoneInfo("UTC"))
            for key, value in product_info_dict.items():
                setattr(existing, key, value)
        else:
            # Create new cache entry
            db_product = Product.from_product_info(product_info)
            db_product.timestamp = datetime.now(ZoneInfo("UTC"))
            db.add(db_product)
    
    db.commit()

@app.post("/get-prices", response_model=PriceResponse)
async def get_prices(request: PriceRequest, db: Session = Depends(get_db)):
    store_name = request.store_name.lower()
    
    if store_name not in SUPPORTED_STORES:
        raise HTTPException(
            status_code=400,
            detail=f"Store '{store_name}' not supported. Supported stores: {', '.join(SUPPORTED_STORES.keys())}"
        )
    
    try:
        # Check cache first
        cached_results = get_cached_results(db, request.urls)
        urls_to_fetch = [url for url in request.urls if str(url) not in cached_results]
        
        if not urls_to_fetch:
            logger.info("All results found in cache")
            return PriceResponse(results=cached_results)
        
        # Check for pending requests
        pending_requests = get_pending_requests(db, store_name, urls_to_fetch)
        urls_to_fetch = [url for url in urls_to_fetch if str(url) not in pending_requests]
        
        if not urls_to_fetch:
            logger.info("All uncached URLs are currently being processed")
            return PriceResponse(
                results=cached_results,
                error="Some URLs are currently being processed. Please try again in a few moments."
            )
        
        # Add new URLs to pending requests
        add_pending_requests(db, store_name, urls_to_fetch)
        
        try:
            # Fetch missing results
            logger.info(f"Creating scraper for store: {store_name}")
            scraper = SUPPORTED_STORES[store_name]()
            
            logger.info(f"Fetching prices for URLs: {urls_to_fetch}")
            new_results = await scraper.get_prices(urls_to_fetch)
            
            # Convert results to ProductInfo objects
            processed_results = {}
            for url, result in new_results.items():
                if result:
                    result['timestamp'] = datetime.now(ZoneInfo("UTC"))
                    processed_results[url] = ProductInfo(**result)
            
            # Cache new results
            cache_results(db, processed_results)
            
            # Remove pending requests
            remove_pending_requests(db, urls_to_fetch)
            
            # Combine cached and new results
            all_results = {**cached_results, **processed_results}
            
            return PriceResponse(results=all_results)
        except Exception as e:
            # Remove pending requests on error
            remove_pending_requests(db, urls_to_fetch)
            raise
            
    except Exception as e:
        logger.error(f"Error processing request: {str(e)}", exc_info=True)
        return PriceResponse(results={}, error=str(e))

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