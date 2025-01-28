from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from app.schemas.request_schemas import PriceRequest, PriceResponse, ProductInfo, RequestStatus, UrlResult
from app.scrapers.costco_scraper import CostcoScraper
from app.scrapers.walmart_scraper import WalmartScraper
from app.scrapers.albertsons_scraper import AlbertsonsScraper
from app.scrapers.chefstore_scraper import ChefStoreScraper
from app.models.database import SessionLocal, Product, PendingRequest, Base, RequestCache
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
logging.basicConfig(level=logging.DEBUG)
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
    logger.debug(f"Checking cache with cutoff_time: {cutoff_time}, tzinfo: {cutoff_time.tzinfo}")
    
    for url in urls:
        cached = (
            db.query(Product)
            .filter(Product.url == str(url))
            .filter(Product.timestamp > cutoff_time)
            .first()
        )
        if cached:
            logger.debug(f"Found cached product with timestamp: {cached.timestamp}, tzinfo: {cached.timestamp.tzinfo}")
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
            
        try:
            # Ensure timestamp is properly set
            current_time = datetime.now(timezone.utc)
            if 'timestamp' not in product_info_dict or product_info_dict['timestamp'] is None:
                product_info_dict['timestamp'] = current_time
            elif isinstance(product_info_dict['timestamp'], str):
                try:
                    product_info_dict['timestamp'] = datetime.fromisoformat(product_info_dict['timestamp'].replace('Z', '+00:00'))
                except ValueError:
                    product_info_dict['timestamp'] = current_time
            elif isinstance(product_info_dict['timestamp'], datetime):
                if product_info_dict['timestamp'].tzinfo is None:
                    product_info_dict['timestamp'] = product_info_dict['timestamp'].replace(tzinfo=timezone.utc)
                else:
                    product_info_dict['timestamp'] = product_info_dict['timestamp'].astimezone(timezone.utc)
            
            logger.debug(f"Product info timestamp before conversion: {product_info_dict['timestamp']}, type: {type(product_info_dict['timestamp'])}")
            
            # Convert dictionary to ProductInfo model
            product_info = ProductInfo(**product_info_dict)
            logger.debug(f"Product info timestamp after conversion: {product_info.timestamp}, tzinfo: {product_info.timestamp.tzinfo}")
                
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
        
        except Exception as e:
            logger.error(f"Error caching results for URL {url}: {str(e)}")
            continue
    
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
        
        # Initialize results dictionary
        final_results = {}
        
        # Clean up stale cache entries
        cleanup_time = datetime.now(timezone.utc) - timedelta(hours=24)
        logger.debug(f"Cleaning up cache with cleanup_time: {cleanup_time}, tzinfo: {cleanup_time.tzinfo}")
        db.query(RequestCache).filter(RequestCache.update_time < cleanup_time).delete()
        db.commit()
        
        # Process each URL
        urls_to_process = []
        for url in urls:
            url_str = str(url)
            now = datetime.now(timezone.utc)
            logger.debug(f"Processing URL {url_str} at time: {now}, tzinfo: {now.tzinfo}")
            
            # Check existing cache entry
            cache_entry = (
                db.query(RequestCache)
                .filter(RequestCache.url == url_str)
                .filter(RequestCache.store == store_name)
                .order_by(RequestCache.update_time.desc())
                .first()
            )
            
            if cache_entry:
                logger.debug(f"Found cache entry - status: {cache_entry.status}, start_time: {cache_entry.start_time}, tzinfo: {cache_entry.start_time.tzinfo}")
                elapsed_time = (now - cache_entry.start_time).total_seconds()
                logger.debug(f"Calculated elapsed_time: {elapsed_time}")
                
                if cache_entry.status == 'completed':
                    # Get from product cache if completed
                    product = (
                        db.query(Product)
                        .filter(Product.url == url_str)
                        .filter(Product.store == store_name)
                        .order_by(Product.timestamp.desc())
                        .first()
                    )
                    
                    status = RequestStatus(
                        status='completed',
                        job_id=cache_entry.job_id,
                        start_time=cache_entry.start_time,
                        elapsed_time_seconds=elapsed_time,
                        remaining_time_seconds=0,
                        price_found=cache_entry.price_found,
                        error_message=cache_entry.error_message,
                        details=f"Request completed in {elapsed_time:.1f} seconds"
                    )
                    
                    if product and not cache_entry.is_stale:
                        logger.debug(f"Using cached product with timestamp: {product.timestamp}, tzinfo: {product.timestamp.tzinfo}")
                        final_results[url_str] = UrlResult(
                            result=product.to_product_info(),
                            request_status=status
                        )
                        continue
                
                elif cache_entry.status == 'pending' and cache_entry.is_active:
                    # Still processing
                    remaining_time = max(0, 600 - elapsed_time)  # 600 seconds = 10 minutes
                    status = RequestStatus(
                        status='running',
                        job_id=cache_entry.job_id,
                        start_time=cache_entry.start_time,
                        elapsed_time_seconds=elapsed_time,
                        remaining_time_seconds=remaining_time,
                        price_found=None,
                        error_message=None,
                        details=f"Request running for {elapsed_time:.1f} seconds, {remaining_time:.1f} seconds remaining"
                    )
                    
                    final_results[url_str] = UrlResult(
                        result=None,
                        request_status=status
                    )
                    continue
                
                elif cache_entry.status in ['failed', 'timeout']:
                    status = RequestStatus(
                        status=cache_entry.status,
                        job_id=cache_entry.job_id,
                        start_time=cache_entry.start_time,
                        elapsed_time_seconds=elapsed_time,
                        remaining_time_seconds=0,
                        price_found=cache_entry.price_found,
                        error_message=cache_entry.error_message,
                        details=f"Request {cache_entry.status} after {elapsed_time:.1f} seconds"
                    )
                    
                    final_results[url_str] = UrlResult(
                        result=None,
                        request_status=status
                    )
                    continue
            
            # URL needs processing
            urls_to_process.append(url)
            
            # Generate a unique job ID
            job_id = f"{store_name}_{int(time.time())}_{len(urls_to_process)}"
            
            # Create pending entry
            new_cache_entry = RequestCache(
                store=store_name,
                url=url_str,
                job_id=job_id,
                status='pending',
                start_time=now,
                update_time=now
            )
            db.add(new_cache_entry)
            db.commit()
            
            # Add pending result with status
            status = RequestStatus(
                status='running',
                job_id=job_id,
                start_time=now,
                elapsed_time_seconds=0,
                remaining_time_seconds=600,  # 10 minutes
                price_found=None,
                error_message=None,
                details="Request just started"
            )
            
            final_results[url_str] = UrlResult(
                result=None,
                request_status=status
            )
        
        # Process new URLs in background if any
        if urls_to_process:
            # Create an instance of the scraper
            scraper = scraper_class()
            
            # Function to process URLs in background
            async def process_urls_background():
                try:
                    logger.info(f"Starting background processing for URLs: {urls_to_process}")
                    
                    try:
                        # Set a 10-minute timeout for the scraping
                        async with asyncio.timeout(600):  # 10 minutes in seconds
                            results = await scraper.get_prices(urls_to_process)
                            
                            # Update cache and store results
                            for url in urls_to_process:
                                url_str = str(url)
                                cache_entry = (
                                    db.query(RequestCache)
                                    .filter(RequestCache.url == url_str)
                                    .filter(RequestCache.store == store_name)
                                    .order_by(RequestCache.update_time.desc())
                                    .first()
                                )
                                
                                if cache_entry:
                                    now = datetime.now(timezone.utc)
                                    price_info = results.get(url_str)
                                    if price_info:
                                        # Update cache entry
                                        cache_entry.status = 'completed'
                                        cache_entry.price_found = True
                                        cache_entry.update_time = now
                                        
                                        # Store in product cache
                                        price_info['timestamp'] = now
                                        cache_results(db, {url_str: price_info})
                                    else:
                                        cache_entry.status = 'completed'
                                        cache_entry.price_found = False
                                        cache_entry.update_time = now
                                        cache_entry.error_message = "Price not found"
                                    
                                    db.commit()
                                    
                    except asyncio.TimeoutError:
                        logger.error("Background processing timed out after 10 minutes")
                        now = datetime.now(timezone.utc)
                        # Update cache entries as timed out
                        for url in urls_to_process:
                            url_str = str(url)
                            cache_entry = (
                                db.query(RequestCache)
                                .filter(RequestCache.url == url_str)
                                .filter(RequestCache.store == store_name)
                                .order_by(RequestCache.update_time.desc())
                                .first()
                            )
                            if cache_entry:
                                cache_entry.status = 'timeout'
                                cache_entry.update_time = now
                                cache_entry.error_message = "Request timed out after 10 minutes"
                        db.commit()
                    except Exception as e:
                        logger.error(f"Error in background processing: {str(e)}")
                        now = datetime.now(timezone.utc)
                        # Update cache entries as failed
                        for url in urls_to_process:
                            url_str = str(url)
                            cache_entry = (
                                db.query(RequestCache)
                                .filter(RequestCache.url == url_str)
                                .filter(RequestCache.store == store_name)
                                .order_by(RequestCache.update_time.desc())
                                .first()
                            )
                            if cache_entry:
                                cache_entry.status = 'failed'
                                cache_entry.update_time = now
                                cache_entry.error_message = str(e)
                        db.commit()
                    
                except Exception as e:
                    logger.error(f"Background task error: {str(e)}")
            
            # Start background processing
            asyncio.create_task(process_urls_background())
        
        # Wait up to 1 minute for immediate results
        if urls_to_process:
            try:
                async with asyncio.timeout(60):  # 1 minute timeout
                    while True:
                        # Check if any URLs are now in product cache
                        new_cached = get_cached_results(db, urls_to_process)
                        if new_cached:
                            for url_str, product_info in new_cached.items():
                                cache_entry = (
                                    db.query(RequestCache)
                                    .filter(RequestCache.url == url_str)
                                    .filter(RequestCache.store == store_name)
                                    .order_by(RequestCache.update_time.desc())
                                    .first()
                                )
                                
                                if cache_entry:
                                    now = datetime.now(timezone.utc)
                                    elapsed_time = (now - cache_entry.start_time).total_seconds()
                                    status = RequestStatus(
                                        status='completed',
                                        job_id=cache_entry.job_id,
                                        start_time=cache_entry.start_time,
                                        elapsed_time_seconds=elapsed_time,
                                        remaining_time_seconds=0,
                                        price_found=cache_entry.price_found,
                                        error_message=cache_entry.error_message,
                                        details=f"Request completed in {elapsed_time:.1f} seconds"
                                    )
                                    
                                    final_results[url_str] = UrlResult(
                                        result=product_info,
                                        request_status=status
                                    )
                            
                            urls_to_process = [url for url in urls_to_process if str(url) not in new_cached]
                            if not urls_to_process:
                                break
                        
                        # Update status for remaining URLs
                        for url in urls_to_process:
                            url_str = str(url)
                            if url_str in final_results:
                                cache_entry = (
                                    db.query(RequestCache)
                                    .filter(RequestCache.url == url_str)
                                    .filter(RequestCache.store == store_name)
                                    .order_by(RequestCache.update_time.desc())
                                    .first()
                                )
                                
                                if cache_entry:
                                    now = datetime.now(timezone.utc)
                                    elapsed_time = (now - cache_entry.start_time).total_seconds()
                                    remaining_time = max(0, 600 - elapsed_time)
                                    
                                    status = RequestStatus(
                                        status='running',
                                        job_id=cache_entry.job_id,
                                        start_time=cache_entry.start_time,
                                        elapsed_time_seconds=elapsed_time,
                                        remaining_time_seconds=remaining_time,
                                        price_found=None,
                                        error_message=None,
                                        details=f"Request running for {elapsed_time:.1f} seconds, {remaining_time:.1f} seconds remaining"
                                    )
                                    
                                    final_results[url_str].request_status = status
                        
                        await asyncio.sleep(5)
            except asyncio.TimeoutError:
                logger.info("Timeout reached, returning partial results with status")
        
        return PriceResponse(results=final_results)
        
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