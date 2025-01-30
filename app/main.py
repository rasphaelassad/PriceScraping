from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from app.schemas.request_schemas import (
    PriceRequest, PriceResponse, ProductInfo, 
    RequestStatusEnum, UrlResult
)
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

@app.get("/health")
def health_check():
    return {'status': 'healthy'}

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

def cache_results(db: Session, results: Dict[str, UrlResult]):
    """Cache successful results in the database"""
    for url, result in results.items():
        if result.status == RequestStatusEnum.SUCCESS and result.product:
            # Check if product exists
            existing = db.query(Product).filter(Product.url == url).first()
            if existing:
                # Update existing product
                existing.name = result.product.name
                existing.price = result.product.price
                existing.price_string = result.product.price_string
                existing.price_per_unit = result.product.price_per_unit
                existing.price_per_unit_string = result.product.price_per_unit_string
                existing.store_id = result.product.store_id
                existing.store_address = result.product.store_address
                existing.store_zip = result.product.store_zip
                existing.brand = result.product.brand
                existing.sku = result.product.sku
                existing.category = result.product.category
                existing.timestamp = datetime.now(timezone.utc)
            else:
                # Create new product
                product = Product(
                    store=result.product.store,
                    url=url,
                    name=result.product.name,
                    price=result.product.price,
                    price_string=result.product.price_string,
                    price_per_unit=result.product.price_per_unit,
                    price_per_unit_string=result.product.price_per_unit_string,
                    store_id=result.product.store_id,
                    store_address=result.product.store_address,
                    store_zip=result.product.store_zip,
                    brand=result.product.brand,
                    sku=result.product.sku,
                    category=result.product.category,
                    timestamp=datetime.now(timezone.utc)
                )
                db.add(product)
    db.commit()

@app.post("/api/v1/prices", response_model=PriceResponse)
async def get_prices(request: PriceRequest, db: Session = Depends(get_db)):
    """Get prices for the requested URLs"""
    if request.store not in SUPPORTED_STORES:
        raise HTTPException(status_code=400, detail=f"Unsupported store: {request.store}")

    logger.info(f"Processing {len(request.urls)} URLs for store: {request.store}")
    
    # Get cached results
    cached_results = get_cached_results(db, [str(url) for url in request.urls])
    urls_to_fetch = [url for url in request.urls if str(url) not in cached_results]

    if not urls_to_fetch:
        logger.info("All results found in cache")
        return PriceResponse(
            results={url: UrlResult(
                status=RequestStatusEnum.SUCCESS,
                product=product
            ) for url, product in cached_results.items()}
        )

    # Check for pending requests
    pending = get_pending_requests(db, request.store, urls_to_fetch)
    urls_to_fetch = [url for url in urls_to_fetch if str(url) not in pending]

    # Add new requests to pending
    add_pending_requests(db, request.store, urls_to_fetch)

    # Initialize results with cached and pending URLs
    results = {}
    for url in request.urls:
        url_str = str(url)
        if url_str in cached_results:
            results[url_str] = UrlResult(
                status=RequestStatusEnum.SUCCESS,
                product=cached_results[url_str]
            )
        elif url_str in pending:
            results[url_str] = UrlResult(
                status=RequestStatusEnum.PENDING
            )

    # Only fetch URLs that are not cached or pending
    if urls_to_fetch:
        try:
            # Initialize scraper
            scraper = SUPPORTED_STORES[request.store]()
            
            # Fetch all prices at once
            products = await scraper.get_prices(urls_to_fetch)
            
            # Process results
            for url in urls_to_fetch:
                url_str = str(url)
                product = products.get(url_str)
                
                if product:
                    results[url_str] = UrlResult(
                        status=RequestStatusEnum.SUCCESS,
                        product=product
                    )
                else:
                    results[url_str] = UrlResult(
                        status=RequestStatusEnum.ERROR,
                        error="Failed to extract product information"
                    )
                    
        except Exception as e:
            logger.error(f"Error scraping URLs: {str(e)}", exc_info=True)
            # Mark all non-processed URLs as error
            for url in urls_to_fetch:
                url_str = str(url)
                if url_str not in results:
                    results[url_str] = UrlResult(
                        status=RequestStatusEnum.ERROR,
                        error=str(e)
                    )

    # Cache successful results
    cache_results(db, results)
        
    # Remove completed requests from pending
    remove_pending_requests(db, urls_to_fetch)

    return PriceResponse(results=results)

@app.get("/api/v1/prices/stores")
def get_supported_stores():
    """Get list of supported stores"""
    return {"supported_stores": list(SUPPORTED_STORES.keys())}

@app.get("/api/v1/prices/raw")
async def get_raw_html(request: PriceRequest, db: Session = Depends(get_db)):
    """Get raw HTML/JSON response without processing"""
    if request.store not in SUPPORTED_STORES:
        raise HTTPException(status_code=400, detail=f"Unsupported store: {request.store}")

    try:
        scraper = SUPPORTED_STORES[request.store]()
        raw_responses = {}

        for url in request.urls:
            try:
                raw_response = await scraper.get_raw_response(str(url))
                raw_responses[str(url)] = raw_response
            except Exception as e:
                logger.error(f"Error getting raw response for {url}: {str(e)}", exc_info=True)
                raw_responses[str(url)] = {"error": str(e)}

        return raw_responses

    except Exception as e:
        logger.error(f"Error in get_raw_html: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))