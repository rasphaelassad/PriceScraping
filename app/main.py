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
from app.routes import health, stores

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

# Serve static files and handle SPA routing
app.mount("/src", StaticFiles(directory="app/static/src"), name="src")
app.mount("/", StaticFiles(directory="app/static", html=True), name="static")

# Include routers
app.include_router(health.router)
app.include_router(stores.router)

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


@app.get("/")
def serve_spa():
    return FileResponse("app/static/index.html")

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