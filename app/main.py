from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from app.schemas.request_schemas import PriceRequest, PriceResponse
from app.scrapers.walmart_scraper import WalmartScraper
from app.scrapers.albertsons_scraper import AlbertsonsScraper
from app.scrapers.chef_store_scraper import ChefStoreScraper
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

@app.get("/")
def hello_world():
    return {'message': 'Hello from FastAPI'}

@app.get("/hello/{name}")
def hello(name: str):
    return {"message": f'Hello from FastAPI, {name}!'}

SUPPORTED_STORES = {
    "walmart": WalmartScraper,
    "albertsons": AlbertsonsScraper,
    "chef_store": ChefStoreScraper
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
        logger.info(f"Creating scraper for store: {store_name}")
        scraper = SUPPORTED_STORES[store_name]()
        
        logger.info(f"Fetching prices for URLs: {request.urls}")
        results = await scraper.get_prices(request.urls)
        
        logger.info(f"Results type: {type(results)}")
        logger.info(f"Results content: {results}")
        
        # Validate that results is a dictionary
        if not isinstance(results, dict):
            logger.error(f"Invalid results type: {type(results)}")
            return PriceResponse(results={}, error="Invalid response format")
        
        # Create response
        response = PriceResponse(results=results)
        logger.info(f"Response created successfully: {response}")
        return response
        
    except Exception as e:
        logger.error(f"Error processing request: {str(e)}", exc_info=True)
        return PriceResponse(results={}, error=str(e))

@app.get("/supported-stores")
def get_supported_stores():
    return {"supported_stores": list(SUPPORTED_STORES.keys())}

@app.get("/health")
def health_check():
    return {"status": "healthy"} 