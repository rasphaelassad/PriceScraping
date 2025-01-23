from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from app.schemas.request_schemas import PriceRequest, PriceResponse, ProductInfo
from app.scrapers.costco_scraper import CostcoScraper
from app.scrapers.walmart_scraper import WalmartScraper
from app.scrapers.albertsons_scraper import AlbertsonsScraper
from app.scrapers.chef_store_scraper import ChefStoreScraper
from app.models.database import SessionLocal, Product
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import logging

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
    "chef_store": ChefStoreScraper,
    "costco": CostcoScraper,
}

def get_cached_results(db: Session, urls: list[str]) -> dict:
    """Get cached results that are less than 24 hours old"""
    cached_products = {}
    cutoff_time = datetime.utcnow() - timedelta(hours=24)
    
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
    """Cache the results in the database. Skip products with null prices."""
    for url, product_info in results.items():
        if not product_info or product_info.price is None:
            logger.info(f"Skipping product with null price for URL: {url}")
            continue
            
        # Check if product exists in cache
        existing = db.query(Product).filter(Product.url == url).first()
        if existing:
            # Update existing cache entry
            for key, value in product_info.dict().items():
                setattr(existing, key, value)
        else:
            # Create new cache entry
            db_product = Product.from_product_info(product_info)
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
        
        # Fetch missing results
        logger.info(f"Creating scraper for store: {store_name}")
        scraper = SUPPORTED_STORES[store_name]()
        
        logger.info(f"Fetching prices for URLs: {urls_to_fetch}")
        new_results = await scraper.get_prices(urls_to_fetch)
        
        # Convert results to ProductInfo objects
        processed_results = {}
        for url, result in new_results.items():
            if result:
                result['timestamp'] = datetime.utcnow()
                processed_results[url] = ProductInfo(**result)
        
        # Cache new results
        cache_results(db, processed_results)
        
        # Combine cached and new results
        all_results = {**cached_results, **processed_results}
        
        return PriceResponse(results=all_results)
        
    except Exception as e:
        logger.error(f"Error processing request: {str(e)}", exc_info=True)
        return PriceResponse(results={}, error=str(e))

@app.get("/supported-stores")
def get_supported_stores():
    return {"supported_stores": list(SUPPORTED_STORES.keys())}

@app.get("/health")
def health_check():
    return {"status": "healthy"} 