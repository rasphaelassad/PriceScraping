from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from .schemas.request_schemas import PriceRequest, PriceResponse
from .scrapers.walmart_scraper import WalmartScraper
from .scrapers.albertsons_scraper import AlbertsonsScraper
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

SUPPORTED_STORES = {
    "walmart": WalmartScraper,
    "albertsons": AlbertsonsScraper
}

@app.post("/get-prices", response_model=PriceResponse)
async def get_prices(request: PriceRequest):
    store_name = request.store_name.lower()
    
    if store_name not in SUPPORTED_STORES:
        raise HTTPException(
            status_code=400,
            detail=f"Store '{store_name}' not supported. Supported stores: {', '.join(SUPPORTED_STORES.keys())}"
        )
    
    try:
        scraper = SUPPORTED_STORES[store_name]()
        results = await scraper.get_prices(request.urls)
        return PriceResponse(results=results)
    except Exception as e:
        logger.error(f"Error processing request: {str(e)}", exc_info=True)
        return PriceResponse(results={}, error=str(e))

@app.get("/supported-stores")
async def get_supported_stores():
    return {"supported_stores": list(SUPPORTED_STORES.keys())}

@app.get("/health")
async def health_check():
    return {"status": "healthy"} 