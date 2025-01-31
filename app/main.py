from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import inspect
from datetime import datetime, timedelta, timezone
from typing import Dict, Any
import logging
import asyncio

from app.schemas.request_schemas import PriceRequest, PriceResponse, ProductInfo, RequestStatus, UrlResult
from app.models.database import SessionLocal, Product, PendingRequest, RequestCache
from app.scrapers.costco_scraper import CostcoScraper
from app.scrapers.walmart_scraper import WalmartScraper
from app.scrapers.albertsons_scraper import AlbertsonsScraper
from app.scrapers.chefstore_scraper import ChefStoreScraper

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

# Static files - serve the built frontend
app.mount("/", StaticFiles(directory="app/static", html=True), name="static")

# Store configurations
SUPPORTED_STORES = {
    "walmart": WalmartScraper,
    "albertsons": AlbertsonsScraper,
    "chefstore": ChefStoreScraper,
    "costco": CostcoScraper,
}

# Database dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Cache management functions
def get_cached_results(db: Session, urls: list[str]) -> dict:
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

def cache_results(db: Session, results: dict):
    for url, product_info_dict in results.items():
        if not product_info_dict or product_info_dict.get('price') is None:
            logger.info(f"Skipping product with null price for URL: {url}")
            continue

        product_info_dict['timestamp'] = datetime.now(timezone.utc)
        product_info = ProductInfo(**product_info_dict)
        url_str = str(url)

        existing = db.query(Product).filter(Product.url == url_str).first()
        if existing:
            for key, value in product_info_dict.items():
                setattr(existing, key, value)
        else:
            db_product = Product.from_product_info(product_info)
            db.add(db_product)

    db.commit()

# Routes
@app.get("/")
def serve_spa():
    return FileResponse("app/static/index.html")

@app.post("/api/get-prices")
async def get_prices(request: PriceRequest, db: Session = Depends(get_db)):
    try:
        store_name = request.store_name.lower()
        urls = request.urls
        final_results = {}
        now = datetime.now(timezone.utc)

        if store_name not in SUPPORTED_STORES:
            raise HTTPException(status_code=400, detail=f"Unsupported store: {store_name}")

        scraper = SUPPORTED_STORES[store_name]()

        for url in urls:
            url_str = str(url)

            # Check cache first
            cached_product = (
                db.query(Product)
                .filter(Product.url == url_str)
                .filter(Product.store == store_name)
                .filter(Product.timestamp > now - timedelta(hours=24))
                .first()
            )

            if cached_product:
                status = RequestStatus(
                    status='completed',
                    start_time=cached_product.timestamp,
                    elapsed_time_seconds=0,
                    remaining_time_seconds=0,
                    price_found=True,
                    details="Cached result"
                )
                final_results[url_str] = UrlResult(
                    result=cached_product.to_product_info(),
                    request_status=status
                )
                continue

            # Start new scraping job
            api_response = await scraper._start_scraper_job(url_str)
            job_id = api_response.get('id')

            if not job_id:
                status = RequestStatus(
                    status='failed',
                    start_time=now,
                    elapsed_time_seconds=0,
                    remaining_time_seconds=0,
                    price_found=False,
                    error_message="Failed to get job ID"
                )
                final_results[url_str] = UrlResult(result=None, request_status=status)
                continue

            # Create request cache entry
            cache_entry = RequestCache(
                store=store_name,
                url=url_str,
                job_id=job_id,
                status='pending',
                start_time=now,
                update_time=now
            )
            db.add(cache_entry)
            db.commit()

            status = RequestStatus(
                status='running',
                job_id=job_id,
                start_time=now,
                elapsed_time_seconds=0,
                remaining_time_seconds=600,
                price_found=None,
                details="Request started"
            )
            final_results[url_str] = UrlResult(result=None, request_status=status)

        return PriceResponse(results=final_results)

    except Exception as e:
        logger.error(f"Error processing request: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/supported-stores")
def get_supported_stores():
    return {"supported_stores": list(SUPPORTED_STORES.keys())}

@app.get("/api/health")
def health_check():
    return {"status": "healthy"}

@app.get("/tables")
def get_tables(db: Session = Depends(get_db)):
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
    try:
        store_name = request.store_name.lower()
        if store_name not in SUPPORTED_STORES:
            raise HTTPException(status_code=400, detail=f"Unsupported store: {store_name}")

        scraper = SUPPORTED_STORES[store_name]()
        raw_results = await scraper.get_raw_content(request.urls)
        return JSONResponse(content=raw_results)

    except Exception as e:
        logger.error(f"Error processing raw scrape request: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

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

def get_pending_requests(db: Session, store: str, urls: list[str]) -> dict:
    """Get URLs that are currently being processed"""
    pending = {}
    try:
        # Clean up old pending requests (older than 10 minutes)
        cleanup_time = datetime.now(timezone.utc) - timedelta(minutes=10)
        db.query(PendingRequest).filter(PendingRequest.timestamp < cleanup_time).delete()
        db.commit()
    except Exception as e:
        logger.error(f"Error cleaning up pending requests: {str(e)}")
        db.rollback()
    
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